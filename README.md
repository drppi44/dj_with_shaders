## Running the application
Python version is 3.7.5

`python -m autodj.main`

Use `space` to trigger shader and `enter` to change shader. 
## DJ commands

To run the application, run the `main.py` script in the `AIDJ-python3/Application` directory:

`python main.py`

The application is controlled using commands. The following commands are available:

* `loaddir <directory>` : Add the _.wav_ and _.mp3_ audio files in the specified directory to the pool of available songs.
* `annotate` : Annotate all the files in the pool of available songs that are not annotated yet. Note that this might take a while, and that in the current prototype this can only be interrupted by forcefully exiting the program (using the key combination `Ctrl+C`).
* `play` : Start a DJ mix. This command must be called after using the `loaddir` command on at least one directory with some annotated songs. Also used to continue playing after pausing. ( run : "play save" can save the set)
* `pause` : Pause the DJ mix.
* `stop` : Stop the DJ mix.
* `skip` : Skip to the next important boundary in the mix. This skips to either the beginning of the next crossfade, the switch point of the current crossfade or the end of the current crossfade, whichever comes first.
* `s` : Shorthand for the skip command
* `showannotated` : Shows how many of the loaded songs are annotated.
* `debug` : Toggle debug information output. This command must be used before starting playback, or it will have no effect.

To exit the application, use the `Ctrl+C` key combination.

## Copyright information
Copyright 2017 Len Vande Veire, IDLab, Department of Electronics and Information Systems, Ghent University.

This file is part of the source code for the Auto-DJ research project, published in Vande Veire, Len, and De Bie, Tijl, "From raw audio to a seamless mix: an artificial intelligence approach to creating an automated DJ system." 2018 (submitted).

Released under AGPLv3 license.
