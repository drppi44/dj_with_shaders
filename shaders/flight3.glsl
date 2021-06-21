
uniform float time;
uniform vec2 mouse;
uniform vec2 resolution;
uniform float beat;

struct Camera {
    vec3 pos;
    mat3 ori;
};

// https://www.shadertoy.com/view/4djSRW
vec3 Hash13(in float t) {
   vec3 p3 = fract(t * vec3(0.1031, 0.1030, 0.0973));
   p3 += dot(p3, p3.yzx + 33.33);
   return fract((p3.xxy + p3.yzz) * p3.zyx);
}

Camera getCamera(in float t) {
    float id = floor(t), local = fract(t);
    vec3 a = Hash13(id), b = Hash13(id + 1.0), c = Hash13(id + 2.0);
    vec3 mid1 = 0.5 * (a + b), mid2 = 0.5 * (b + c);

    float tInv = 1.0 - local;
    vec3 pos = mid1 * tInv * tInv + 2.0 * b * tInv * local + mid2 * local * local;

    vec3 f = normalize(mid1 * (local - 1.0) + (1.0 - 2.0 * local) * b + mid2 * local);
    vec3 r = vec3(-f.z, 0.0, f.x) / sqrt(1.0 - f.y * f.y);
    vec3 u = cross(r, f);

    return Camera(pos, mat3(r, u, f));
}


mat3 invOrthoNormBasis(in mat3 m) {
    return mat3(m[0][0], m[1][0], m[2][0],
		m[0][1], m[1][1], m[2][1],
		m[0][2], m[1][2], m[2][2]);
}

void main(void) {
    vec2 uv = (gl_FragCoord.xy - 0.5 * resolution) / resolution.y;
    float v = 0.;
    //gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
    float beatVal = sqrt(beat);

    Camera cam = getCamera(time * 0.25);

    vec3 ro = cam.pos * 100.0 - 50.0;
    vec3 rd = normalize(vec3(uv, 1.0)) * invOrthoNormBasis(cam.ori);

    float t = 0.0;
    for (int i=0; i < 100; i++) {
        vec3 p = ro + rd * t;
        vec3 pMod = mod(p, 2.0) - 1.0;
        float d = length(pMod) - 0.25 - 0.1*beatVal;
        if (d < 0.001) {
            vec3 n = pMod * 4.0;
            vec3 l = vec3(sqrt(1.0 / 3.0));
            v += max(0.0, mix(dot(n, l), dot(n, -rd), 0.5));
            break;
        }

        if (t > 100.0) {
            break;
        }

        t += d;
    }
    // vec3 beatColor = vec3(sqrt(abs(sin(time))), sqrt(abs(cos(time))), 0.8);
    const vec3 normalColor = vec3(1., 1., 1.);

    gl_FragColor = vec4(normalColor*v, 1.0);
}