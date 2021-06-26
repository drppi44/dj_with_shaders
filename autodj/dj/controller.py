# Copyright 2017 Len Vande Veire, IDLab, Department of Electronics and Information Systems, Ghent University
# This file is part of the source code for the Auto-DJ research project, published in Vande Veire, Len, and De Bie, Tijl, "From raw audio to a seamless mix: an artificial intelligence approach to creating an automated DJ system.", 2018 (submitted)
# Released under AGPLv3 license.
import random
import time

import numpy as np
import bisect

# For threading and queueing of songs
import multiprocessing
from multiprocessing import Process, Queue
import ctypes
from time import sleep
# For live playback of songs
import pyaudio

from . import tracklister
from . import songtransitions
from .timestretching import time_stretch_and_pitch_shift

import logging

from .tracklister import NUM_SONGS_IN_KEY_MINIMUM

logger = logging.getLogger('colorlogger')

import os
import csv

from essentia.standard import MonoWriter, AudioWriter
from ..shaderview import ShaderView

class DjController:
	
	def __init__(self, tracklister, stereo=True):
		self.tracklister = tracklister
		self.stereo = stereo

		self.audio_thread = None
		self.dj_thread = None
		self.playEvent = multiprocessing.Event()
		self.isPlaying = multiprocessing.Value('b', True)
		self.skipFlag = multiprocessing.Value('b', False)
		self.queue = Queue(6)				# A blocking queue of to pass at most N audio fragments between audio thread and generation thread
		self.visual_queue = Queue(6)
		self.choose_track_case = multiprocessing.Value('i', 0)

		self.currentMasterString = multiprocessing.Manager().Value(ctypes.c_char_p, '')
		
		self.pyaudio = None
		self.stream = None
		
		self.djloop_calculates_crossfade = False
		
		self.save_mix = False
		self.save_dir_idx = 0
		self.save_dir = './mix_{}.wav'
		self.save_dir_tracklist = './mix.txt'
		self.audio_to_save = None
		self.audio_save_queue = Queue(6)
		self.save_tracklist = []

	def play(self, save_mix = False):
								
		self.playEvent.set()
			
		if self.dj_thread is None and self.audio_thread is None:
			self.save_mix = save_mix
			self.save_dir_idx = 0
			self.audio_to_save = []
			self.save_tracklist = []
			
			# if self.save_mix:
			# 	Process(target = self._flush_save_audio_buffer, args=(self.audio_save_queue,)).start()
			
			self.dj_thread = Process(target = self._dj_loop, args=(self.isPlaying,))
			self.audio_thread = Process(target = self._audio_play_loop, args=(self.playEvent, self.isPlaying, self.currentMasterString))
			self.visual_thread = Process(target=ShaderView.run, args=(self.visual_queue,))
			self.isPlaying.value = True
			self.dj_thread.start()

			while self.queue.empty():
				# wait until the queue is full
				sleep(0.1)
				
			self.audio_thread.start()
			self.visual_thread.start()
			
		elif self.dj_thread is None or self.audio_thread is None:
			raise Exception('dj_thread and audio_thread are not both Null!')
	
	def save_audio_to_disk(self, audio, song_title):
		
		self.audio_to_save.append(audio)
		self.save_tracklist.append(song_title)
		
		if np.sum([len(a) for a in self.audio_to_save]) > 44100 * 60 * 15:
			self.flush_audio_to_queue()
			
	def flush_audio_to_queue(self):
		self.save_dir_idx += 1
		self.audio_to_save = np.concatenate(self.audio_to_save, axis=-1)
		self.audio_save_queue.put((self.save_dir.format(self.save_dir_idx), np.array(self.audio_to_save,dtype='single'), self.save_tracklist))
		self.audio_to_save = []
		self.save_tracklist = []
			
	def skipToNextSegment(self):
		if not self.queue.empty():
			self.skipFlag.value = True
		else:
			self.skipFlag.value = False
			logger.warning('Cannot skip to next segment, no audio in queue!')
			
	def markCurrentMaster(self):
		with open('markfile.csv','a+') as csvfile:
			writer = csv.writer(csvfile)
			writer.writerow([self.currentMasterString.value])
		logger.debug('{:20s} has been marked for manual annotation.'.format(self.currentMasterString.value))
	
	def pause(self):
		if self.audio_thread is None:
			return
		self.playEvent.clear()

	def pick_track(self, value):
		self.choose_track_case.value = value

	def stop(self):
		# If paused, then continue playing (deadlock prevention)
		try:
			self.playEvent.set()
		except Exception as e:
			logger.debug(e)
		# Notify the threads to stop working
		self.isPlaying.value = False
		# Empty the queue so the dj thread can terminate
		while not self.queue.empty():
			self.queue.get_nowait()
		if not self.dj_thread is None:
			self.dj_thread.terminate()
		# Reset the threads
		self.queue = Queue(6)
		self.audio_thread = None
		self.dj_thread = None
		# Reset pyaudio resources
		if not self.stream is None:
			self.stream.stop_stream()
			self.stream.close()
		if not self.pyaudio is None:
			self.pyaudio.terminate()
		self.pyaudio = None
			
	def _audio_play_loop(self, playEvent, isPlaying, currentMasterString):
		
		if self.pyaudio is None:
			# Open the audio
			self.pyaudio = pyaudio.PyAudio()
			
		if self.stream is None:
			self.stream = self.pyaudio.open(format = pyaudio.paFloat32,
						channels=1 if not self.stereo else 2,
						rate=44100,
						output=True)
						
		while isPlaying.value:
			toPlay, toPlayStr, masterTitle, beats, current_audio_start = self.queue.get()
			current_audio_start /= 44100
			logger.info(toPlayStr)
			currentMasterString.value = masterTitle
			if toPlay is None:
				break
			else:
				# Save the audio if necessary
				if self.save_mix:
					self.save_audio_to_disk(toPlay, masterTitle)

			FRAME_LEN = 1024
			last_frame_start_idx = int(toPlay.shape[-1]/FRAME_LEN) * FRAME_LEN

			from time import time
			start = None
			for cur_idx in range(0,last_frame_start_idx+1,FRAME_LEN):
				playEvent.wait()
				if not start:
					start = time()

				if not self.isPlaying.value:
					break
				if self.skipFlag.value:
					self.skipFlag.value = False
					break
				if cur_idx == last_frame_start_idx:
					end_idx = toPlay.shape[-1]
				else:
					end_idx = cur_idx + FRAME_LEN
				toPlayNow = toPlay[..., cur_idx:end_idx]
				if toPlayNow.dtype != 'float32':
					toPlayNow = toPlayNow.astype('float32')
				toPlayNow = np.copy(toPlayNow.T, order='C')

				current_track_position = time() - start + current_audio_start
				if len(beats) and current_track_position > beats[0]:
					# print(f'Removing beats[0]: {beats[0]} from beats list and trigger Beat! {len(beats)}')
					del beats[0]
					self.visual_queue.put('Beat')

				self.stream.write(toPlayNow, num_frames=toPlayNow.shape[0], exception_on_underflow=False)

		logger.debug('Stopping music')
		if self.save_mix:
			logger.debug('Flushing audio to disk...')
			self.flush_audio_to_queue()
			self.audio_save_queue.put((None, None, None))

	def _dj_loop(self, isPlaying):
		
		TEMPO = 175 # Keep tempo fixed for classification of audio in segment evaluation
		samples_per_dbeat = 44100 * 4 * 60.0 / TEMPO
		
		# Array with all songs somewhere in queue at the moment (playing or to be played)
		song_titles_in_buffer = []
		# Sorted list of fade in points in samples relative to start of buffer
		tracklist_changes = []
		# The total number of songs hearable right now
		num_songs_playing = 0
		# The idx of the master in the subset of songs that is playing right now
		songs_playing_master = 0
		
		def add_song_to_tracklist(master_song, anchor_sample, next_song, next_fade_type, cue_master_out, fade_in_len, fade_out_len):
			f = master_song.tempo / TEMPO			
			buffer_in_sample = int(f * (44100 * master_song.downbeats[cue_master_out] - anchor_sample))
			buffer_switch_sample = int(f * (44100 * master_song.downbeats[cue_master_out] - anchor_sample) + fade_in_len * samples_per_dbeat)
			buffer_out_sample = int(f * (44100 * master_song.downbeats[cue_master_out] - anchor_sample) + (fade_in_len + fade_out_len) * samples_per_dbeat)
			
			song_titles_in_buffer.append(next_song.title)
			bisect.insort(tracklist_changes, (buffer_in_sample,'in',next_fade_type))		# Marks the moment from which there's one song more
			bisect.insort(tracklist_changes, (buffer_switch_sample,'switch',next_fade_type))# Marks the moment from which there's a switch in master
			bisect.insort(tracklist_changes, (buffer_out_sample,'out',next_fade_type))		# Marks the moment from which there's one song less
			
		def curPlayingString(fade_type_str):
			
			outstr = 'Now playing:\n'
			for i in range(num_songs_playing):
				if i != songs_playing_master:
					outstr += song_titles_in_buffer[i] + '\n'
				else:
					outstr += song_titles_in_buffer[i].upper() + '\n'
			if fade_type_str != '':
				outstr += '['+fade_type_str+']'
			return outstr
			
			
		if self.save_mix:
			self.audio_to_save = []
			self.save_tracklist = []
		
		# Set parameters for the first song
		current_song = self.tracklister.getFirstSong()
		current_song.open()
		current_song.openAudio()
		anchor_sample = 0
		cue_master_in = current_song.segment_indices[0] # Start at least 32 downbeat into the first song, enough time to fill the buffer
		fade_in_len = 16
		prev_fade_type = tracklister.TYPE_CHILL
		logger.debug('FIRST SONG: {}'.format(current_song.title))
		
		cue_master_out, next_fade_type, max_fade_in_len, fade_out_len = tracklister.getMasterQueue(current_song, cue_master_in + fade_in_len, prev_fade_type)
		next_song, cue_next_in, cue_master_out, fade_in_len, semitone_offset = self.tracklister.getBestNextSongAndCrossfade(current_song, cue_master_out, max_fade_in_len, fade_out_len, next_fade_type)		
		song_titles_in_buffer.append(current_song.title)
		add_song_to_tracklist(current_song, anchor_sample, next_song, next_fade_type, cue_master_out, fade_in_len, fade_out_len)
		prev_in_or_out = 'in'
			
		f = current_song.tempo / TEMPO		
		print(f'CURRENT SONG TEMPO, STRETCH: {current_song.tempo} {f}')
		current_audio_start = 0
		current_audio_end = int((current_song.downbeats[cue_master_out] * 44100) + (fade_in_len + fade_out_len + 2)*samples_per_dbeat/f)
		if self.stereo:
			current_audio_stretched = np.array((
				time_stretch_and_pitch_shift(np.asfortranarray(current_song.audio_left[current_audio_start:current_audio_end]), f),
				time_stretch_and_pitch_shift(np.asfortranarray(current_song.audio_right[current_audio_start:current_audio_end]), f)
			))
		else:
			current_audio_stretched = time_stretch_and_pitch_shift(current_song.audio[current_audio_start:current_audio_end], f)
		
		mix_buffer = current_audio_stretched
		mix_buffer_cf_start_sample = int(f * (current_song.downbeats[cue_master_out] * 44100))
		while True:
			# Cue the audio from the previous event point till the current event point.
			# The "type" of audio (one song added, one song less, or change of master) is determined
			# by the label of the previous event in the audio buffer
			prev_end_sample = 0

			for end_sample, in_or_out, cur_fade_type in tracklist_changes:
				if end_sample > mix_buffer_cf_start_sample:
					break	
						
				if prev_in_or_out == 'in':
					num_songs_playing += 1
				elif prev_in_or_out == 'out':
					num_songs_playing -= 1
					songs_playing_master -= 1
					song_titles_in_buffer = song_titles_in_buffer[1:]
				elif prev_in_or_out == 'switch':
					songs_playing_master += 1
				prev_in_or_out = in_or_out
				
				# If its a double drop, then end_sample and prev_end_sample might be the same! Don't queue empty segments..
				if end_sample > prev_end_sample:
					toPlay = mix_buffer[..., prev_end_sample : end_sample]
					cur_fade_type_str = cur_fade_type if num_songs_playing > 1 else ''

					# beat_delay = current_song.beats[1]
					# current_audio_start
					beats = [b for b in current_song.beats if b > current_audio_start / 44100]
					# downbeats = [db for db in current_song.downbeats if db > current_audio_start / 44100]
					toPlayTuple = (toPlay,curPlayingString(cur_fade_type_str), song_titles_in_buffer[songs_playing_master], beats, current_audio_start)
					# Play this audio
					self.queue.put(toPlayTuple, isPlaying.value)	# Block until slot available, unless audio has stopped: this might raise an exception which is caught below
					prev_end_sample = end_sample
					
			tracklist_changes = [(tc[0] - mix_buffer_cf_start_sample, tc[1],tc[2]) for tc in tracklist_changes if tc[0] > mix_buffer_cf_start_sample]	
			mix_buffer = mix_buffer[..., mix_buffer_cf_start_sample : ]
			current_song.close()
			
			# Go to next song, and select the song after that
			current_song = next_song
			current_song.open()
			f = current_song.tempo / TEMPO	
			cue_master_in = cue_next_in
			prev_fade_type = next_fade_type
			prev_fade_in_len = fade_in_len
			prev_fade_out_len = fade_out_len
			
			cue_master_out, next_fade_type, max_fade_in_len, fade_out_len = tracklister.getMasterQueue(current_song, cue_master_in + fade_in_len, prev_fade_type)

			next_song, cue_next_in, cue_master_out, fade_in_len, semitone_offset = self.tracklister.getBestNextSongAndCrossfade(
				current_song, cue_master_out, max_fade_in_len, fade_out_len, next_fade_type)

			if random.randint(0, 100) <= 100:
				next_song_2, cue_next_in_2, cue_master_out_2, fade_in_len_2, semitone_offset_2 = self.tracklister.getBestNextSongAndCrossfade(
					current_song, cue_master_out, max_fade_in_len, fade_out_len, next_fade_type)

				logger.info(f'Type "1" for {next_song.title}.')
				logger.info(f'Type "2" for {next_song_2.title}.')
				i = 15
				while True:
					if self.choose_track_case.value:
						if self.choose_track_case.value == 1:
							...
							# self.tracklister.songsPlayed.remove(next_song_2)
							# self.tracklister.songsUnplayed.append(next_song_2)
						elif self.choose_track_case.value == 2:
							# self.tracklister.songsPlayed.remove(next_song)
							# self.tracklister.songsUnplayed.append(next_song)

							next_song = next_song_2
							cue_next_in = cue_next_in_2
							cue_master_out = cue_master_out_2
							fade_in_len = fade_in_len_2
							semitone_offset = semitone_offset_2
						self.choose_track_case.value = 0
						break
					else:
						time.sleep(1)
						logger.info(i)
						i -= 1
						if i < 0:
							# self.tracklister.songsPlayed.remove(next_song_2)
							# self.tracklister.songsUnplayed.append(next_song_2)
							break

			self.tracklister.semitone_offset = semitone_offset
			if len(self.tracklister.songsUnplayed) <= NUM_SONGS_IN_KEY_MINIMUM:  # If there are too few songs remaining, then restart
				logger.debug('Replenishing song pool')
				self.tracklister.songsUnplayed.extend(self.tracklister.songsPlayed)
				self.tracklister.songsPlayed = []
			logger.info(f'Nex track selected: {next_song.title}.')

			anchor_sample = int(44100 * current_song.downbeats[cue_master_in])
			add_song_to_tracklist(current_song, anchor_sample, next_song, next_fade_type, cue_master_out, fade_in_len, fade_out_len)	
			mix_buffer_cf_start_sample = int(f * (current_song.downbeats[cue_master_out] * 44100 - anchor_sample))
			
			f = current_song.tempo / TEMPO		
			current_song.openAudio()

			current_audio_start = int(current_song.downbeats[cue_master_in] * 44100)
			current_audio_end = int((current_song.downbeats[cue_master_out] * 44100) + (fade_in_len + fade_out_len + 2)*samples_per_dbeat/f) # 2 downbeats margin

			if self.stereo:
				current_audio_stretched = np.array((
					time_stretch_and_pitch_shift(np.asfortranarray(current_song.audio_left[current_audio_start:current_audio_end]), f,
												 semitones=semitone_offset),
					time_stretch_and_pitch_shift(np.asfortranarray(current_song.audio_right[current_audio_start:current_audio_end]), f,
												 semitones=semitone_offset)
				))
			else:
				current_audio_stretched = time_stretch_and_pitch_shift(
					current_song.audio[current_audio_start:current_audio_end], f, semitones=semitone_offset)

			# Calculate crossfade between *previous* song and current song
			cf = songtransitions.CrossFade(0, [0], prev_fade_in_len + prev_fade_out_len, prev_fade_in_len, prev_fade_type)
			if self.stereo:
				mix_buffer_deepcpy = np.array(mix_buffer, dtype='single', copy=True)
				mix_buffer_left = cf.apply(mix_buffer_deepcpy[0], current_audio_stretched[0], TEMPO)
				mix_buffer_right = cf.apply(mix_buffer_deepcpy[1], current_audio_stretched[1], TEMPO)
				mix_buffer = np.array((mix_buffer_left, mix_buffer_right), dtype='single', copy=True)
			else:
				mix_buffer_deepcpy = np.array(mix_buffer, dtype='single', copy=True)
				mix_buffer = cf.apply(mix_buffer_deepcpy, current_audio_stretched, TEMPO)
