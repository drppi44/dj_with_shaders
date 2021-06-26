# shader = 'flight'
# shader = 'sphere'
# shader = 'flight2'
# shader = 'spring'
# shader = 'flight3'
# shader = 'milk'
#shader = 'dancers'
from multiprocessing import Queue

shader = 'Truchet_Tentacles'

shaders = [
    'flight',
    'sphere',
    'flight2',
    'spring',
    'flight3',
    'milk',
    'dancers',
    'Truchet_Tentacles',
]


import os

import numpy as np
import moderngl
import numpy as np

import moderngl_window as mglw



vertex_shader = """
#version 330
in vec2 vert;

uniform vec2 scale;
uniform float rotation;
uniform float time;

void main() {
    gl_Position = vec4(vert, 0.0, 1.0);
}
"""


fragment_shader = open(f'shaders/{shader}.glsl').read()

class Shader:
    def __init__(self, ctx, fn):
        self.ctx = ctx
        self.prog = self.ctx.program(
                    vertex_shader=vertex_shader,
                    fragment_shader=open(f'shaders/{fn}.glsl').read(),
                )
        self.time = self.prog['time']
        self.resolution = self.prog['resolution']
        self.beat = self.prog.get('beat', None)

    def update(self, resolution, time, beat):
        self.resolution.value = mglw.window().size
#        self.rotation.value = time
        self.time.value = time

        if self.beat:
            self.beat.value = beat


class ShaderView(mglw.WindowConfig):
    gl_version = (3, 3)

    title = "Shader View"
    # window_size = (1280, 720)
    # aspect_ratio = 16 / 9
    aspect_ratio = None
    resizable = True
    clear_color = None
    cursor = None
    f = None

    @classmethod
    def run(cls, visual_queue: Queue):
        cls.visual_queue = visual_queue
        mglw.run_window_config(cls)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.shaders = [Shader(self.ctx, shader) for shader in shaders]
        self.shader_idx = 0
        # self.shader1 = Shader(self.ctx, shader)
        # self.shader2 = Shader(self.ctx, 'milk')
        # self.prog = self.ctx.program(
        #     vertex_shader=vertex_shader,
        #     fragment_shader=fragment_shader,
        # )

        # self.prog2 = self.ctx.program(
        #     vertex_shader=vertex_shader,
        #     fragment_shader=open(f'shaders/milk.glsl').read(),
        # )

        # for name in self.prog:
        #     print(name)
        #     member = self.prog[name]
        #     print(name, type(member), member)


        # self.time = self.prog['time']
        # self.resolution = self.prog['resolution']
        # self.beat = self.prog.get('beat', None)
        self.beat_val = 0
        self.i = 0

        #        self.scale.value = (self.wnd.width / self.wnd.height * 0.75, 0.25)

        vertices = np.array(
            [
                -1.0,
                -1.0,
                -1.0,
                1.0,
                1.0,
                1.0,
                #                1., -1.
                -1.0,
                -1.0,
                1.0,
                1.0,
                1.0,
                -1.0
                #            1.0, 0.0,
                #            -0.5, 0.86,
                #            -0.5, -0.86,
            ],
            dtype="f4",
        )

        self.vbo = self.ctx.buffer(vertices)
        # self.vao = self.ctx.simple_vertex_array(self.shaders[self.shader_idx].prog, self.vbo, "vert")
        # self.vao2 = self.ctx.simple_vertex_array(self.shader2.prog, self.vbo, "vert")
        self._update_vao()

    def _update_vao(self):
        self.vao = self.ctx.simple_vertex_array(self.shaders[self.shader_idx].prog, self.vbo, "vert")

    def render(self, time: float, frame_time: float):
        # sin_scale = np.sin(np.deg2rad(time * 60))
        #self.ctx.clear(0., 0., 0.) #1.0, 1.0, 1.0)




        # self.shader1.update(mglw.window().size, time, self.beat_val)
        # self.shader2.update(mglw.window().size, time, self.beat_val)

        self.beat_val *= 0.9

        # if not self.f:
        #     self.f = open('/tmp/f.txt')
        #     self.f.seek(0, 2)
        #
        # line = self.f.readline()
        # if line:
        #     print('beat')
        #     # self.beat_val = 1.
        if not self.visual_queue.empty():
            item = self.visual_queue.get()
            # print(f'Visual got: {item}')
            self.beat_val = 1.

        self.shaders[self.shader_idx].update(mglw.window().size, time, self.beat_val)
        self.vao.render()

    def key_event(self, key, action, modifiers):
        if action == self.wnd.keys.ACTION_PRESS:
            if key == self.wnd.keys.SPACE:
                self.beat_val = 1.
            elif key == self.wnd.keys.ENTER:
                self.shader_idx += 1
                if self.shader_idx >= len(self.shaders):
                    self.shader_idx = 0
                self._update_vao()




# Change the scale of the triangle sin-ly
#        self.scale.value = (sin_scale * 0.75, 0.75)


if __name__ == "__main__":
    ShaderView.run()
