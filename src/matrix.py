r"""Minimal fixed-size linear algebra for the DAE -> rbxmx converter.

Pure stdlib. Conventions:
- 4x4 matrices are row-major lists of 4 rows (each a 4-list) -- COLLADA's layout.
- 3x3 rotations are lists of 3 rows (each a 3-list).
- Vectors are 3-lists.
- glTF node "matrix" arrays are column-major and are transposed on load
  (see rig_read._node_local).
"""

import math


def identity4():
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def identity3():
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def mul4(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def mul3(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mul_vec3(m, v):
    return [m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3)]


def transpose3(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def rot3(m4):
    return [row[:3] for row in m4[:3]]


def trans3(m4):
    return [m4[0][3], m4[1][3], m4[2][3]]


def mat4_from(r3, t):
    return [
        [r3[0][0], r3[0][1], r3[0][2], t[0]],
        [r3[1][0], r3[1][1], r3[1][2], t[1]],
        [r3[2][0], r3[2][1], r3[2][2], t[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def quat_to_mat3(x, y, z, w):
    """glTF quaternion (x, y, z, w) -> row-major 3x3 rotation."""
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return [
        [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
        [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
        [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
    ]


def conj_s3(r):
    r"""Conjugate a 3x3 by S = diag(-1, 1, -1): template axes -> Roblox part axes.

    The template rig faces +Z with left limbs at +X; Roblox faces -Z with left
    at -X (a 180-degree yaw). S maps between them; only the true rotation is
    transferred, so the conjugation applies to pure rotations.
    """
    return [
        [r[0][0], -r[0][1], r[0][2]],
        [-r[1][0], r[1][1], -r[1][2]],
        [r[2][0], -r[2][1], r[2][2]],
    ]


def conj_s_vec(t):
    """Conjugate a translation by S = diag(-1, 1, -1)."""
    return [-t[0], t[1], -t[2]]


def orthonormalize3(r):
    """Gram-Schmidt on rows; repairs scale-contaminated rotation matrices."""
    def norm(v):
        return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

    x = [c / norm(r[0]) for c in r[0]]
    d = r[1][0] * x[0] + r[1][1] * x[1] + r[1][2] * x[2]
    y = [r[1][0] - d * x[0], r[1][1] - d * x[1], r[1][2] - d * x[2]]
    y = [c / norm(y) for c in y]
    z = [
        x[1] * y[2] - x[2] * y[1],
        x[2] * y[0] - x[0] * y[2],
        x[0] * y[1] - x[1] * y[0],
    ]
    return [x, y, z]


def column_scale(m4):
    """Length of the first column of the 3x3 part: the uniform scale baked
    into a node matrix (Mixamo bakes cm->studs as ~100 on the Armature node)."""
    c0 = (m4[0][0], m4[1][0], m4[2][0])
    return math.sqrt(c0[0] * c0[0] + c0[1] * c0[1] + c0[2] * c0[2])
