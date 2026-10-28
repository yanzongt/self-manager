import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import argparse


def get_rotation_matrix(roll, pitch, yaw):
    """
    Generate a rotation matrix from Euler angles (in degrees).
    Using Z-Y-X convention.
    """
    r, p, y = np.radians([roll, pitch, yaw])

    # Rotation about X (roll)
    Rx = np.array([[1, 0, 0], [0, np.cos(r), -np.sin(r)], [0, np.sin(r), np.cos(r)]])

    # Rotation about Y (pitch)
    Ry = np.array([[np.cos(p), 0, np.sin(p)], [0, 1, 0], [-np.sin(p), 0, np.cos(p)]])

    # Rotation about Z (yaw)
    Rz = np.array([[np.cos(y), -np.sin(y), 0], [np.sin(y), np.cos(y), 0], [0, 0, 1]])

    return Rz @ Ry @ Rx


def apply_transform(points, pos, roll, pitch, yaw):
    """
    Apply translation and rotation to a set of points.
    points: (N, 3) array
    """
    R = get_rotation_matrix(roll, pitch, yaw)
    return (R @ points.T).T + np.array(pos)


def plot_lidar_fov(ax, pos, rpy, name="LiDAR", color="cyan", opacity=0.2):
    """
    FOV: 360 horizontal, -7 to 52 vertical.
    """
    r = 2.5  # Visualization radius
    v_min, v_max = -7, 52

    phi = np.linspace(0, 2 * np.pi, 50)
    theta = np.linspace(np.radians(90 - v_max), np.radians(90 - v_min), 20)
    phi_grid, theta_grid = np.meshgrid(phi, theta)

    x = r * np.sin(theta_grid) * np.cos(phi_grid)
    y = r * np.sin(theta_grid) * np.sin(phi_grid)
    z = r * np.cos(theta_grid)

    # Reshape for transformation
    points = np.stack([x, y, z], axis=-1).reshape(-1, 3)
    transformed = apply_transform(points, pos, *rpy)

    tx = transformed[:, 0].reshape(x.shape)
    ty = transformed[:, 1].reshape(y.shape)
    tz = transformed[:, 2].reshape(z.shape)

    surface = ax.plot_surface(tx, ty, tz, color=color, alpha=opacity)
    # Re-enable legend for surface (Matplotlib quirk)
    surface._facecolors2d = surface._facecolor3d
    surface._edgecolors2d = surface._edgecolor3d

    # Wireframe lines (circles at top and bottom)
    for t in [np.radians(90 - v_min), np.radians(90 - v_max)]:
        circ_x = r * np.sin(t) * np.cos(phi)
        circ_y = r * np.sin(t) * np.sin(phi)
        circ_z = np.full_like(phi, r * np.cos(t))
        circ_pts = np.vstack([circ_x, circ_y, circ_z]).T
        t_circ = apply_transform(circ_pts, pos, *rpy)
        ax.plot(t_circ[:, 0], t_circ[:, 1], t_circ[:, 2], color=color, linewidth=1)


def plot_camera_fov(
    ax, pos, rpy, h_fov=86, v_fov=57, d=4.0, name="Camera", color="lime", opacity=0.3
):
    """
    FOV: h_fov x v_fov pyramid.
    """
    h_half = np.radians(h_fov / 2)
    v_half = np.radians(v_fov / 2)

    v0 = [0, 0, 0]
    v1 = [d, d * np.tan(h_half), d * np.tan(v_half)]
    v2 = [d, -d * np.tan(h_half), d * np.tan(v_half)]
    v3 = [d, -d * np.tan(h_half), -d * np.tan(v_half)]
    v4 = [d, d * np.tan(h_half), -d * np.tan(v_half)]

    vertices = np.array([v0, v1, v2, v3, v4])
    transformed = apply_transform(vertices, pos, *rpy)

    # Faces defined by indices
    faces = [
        [transformed[0], transformed[1], transformed[2]],
        [transformed[0], transformed[2], transformed[3]],
        [transformed[0], transformed[3], transformed[4]],
        [transformed[0], transformed[4], transformed[1]],
        [transformed[1], transformed[2], transformed[3], transformed[4]],
    ]

    poly = Poly3DCollection(
        faces, facecolors=color, alpha=opacity, edgecolors=color, linewidths=1
    )
    ax.add_collection3d(poly)


def plot_uss_fov(
    ax, pos, rpy, fov_deg=60, d=2.0, name="USS", color="yellow", opacity=0.4
):
    """
    FOV: Conical circular FOV.
    """
    angle_half = np.radians(fov_deg / 2)
    radius = d * np.tan(angle_half)

    # Cone surface
    h = np.linspace(0, d, 10)
    theta = np.linspace(0, 2 * np.pi, 24)
    H, T = np.meshgrid(h, theta)

    R = H * np.tan(angle_half)
    X = H
    Y = R * np.cos(T)
    Z = R * np.sin(T)

    points = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
    transformed = apply_transform(points, pos, *rpy)

    tx = transformed[:, 0].reshape(X.shape)
    ty = transformed[:, 1].reshape(Y.shape)
    tz = transformed[:, 2].reshape(Z.shape)

    ax.plot_surface(tx, ty, tz, color=color, alpha=opacity)

    # Boundary circle and rays
    # Circle at distance d
    theta_circ = np.linspace(0, 2 * np.pi, 50)
    circ_x = np.full_like(theta_circ, d)
    circ_y = radius * np.cos(theta_circ)
    circ_z = radius * np.sin(theta_circ)
    circ_pts = np.vstack([circ_x, circ_y, circ_z]).T
    t_circ = apply_transform(circ_pts, pos, *rpy)
    ax.plot(t_circ[:, 0], t_circ[:, 1], t_circ[:, 2], color=color, linewidth=1)

    # Rays
    v0 = apply_transform(np.array([[0, 0, 0]]), pos, *rpy)[0]
    for angle in [0, np.pi / 2, np.pi, 3 * np.pi / 2]:
        p_end = np.array([[d, radius * np.cos(angle), radius * np.sin(angle)]])
        t_end = apply_transform(p_end, pos, *rpy)[0]
        ax.plot(
            [v0[0], t_end[0]],
            [v0[1], t_end[1]],
            [v0[2], t_end[2]],
            color=color,
            linewidth=0.5,
        )


def plot_vehicle(ax):
    v_len, v_width, v_height = 0.8, 0.5, 0.3
    v_z_offset = 0.0

    # Vertices
    v = np.array(
        [
            [-v_len / 2, -v_width / 2, v_z_offset],
            [v_len / 2, -v_width / 2, v_z_offset],
            [v_len / 2, v_width / 2, v_z_offset],
            [-v_len / 2, v_width / 2, v_z_offset],
            [-v_len / 2, -v_width / 2, v_z_offset + v_height],
            [v_len / 2, -v_width / 2, v_z_offset + v_height],
            [v_len / 2, v_width / 2, v_z_offset + v_height],
            [-v_len / 2, v_width / 2, v_z_offset + v_height],
        ]
    )

    faces = [
        [v[0], v[1], v[5], v[4]],
        [v[1], v[2], v[6], v[5]],
        [v[2], v[3], v[7], v[6]],
        [v[3], v[0], v[4], v[7]],
        [v[0], v[1], v[2], v[3]],
        [v[4], v[5], v[6], v[7]],
    ]
    ax.add_collection3d(
        Poly3DCollection(faces, facecolors="gray", alpha=0.5, edgecolors="black")
    )


def plot_ground(ax):
    g_len, g_width = 10.0, 10.0
    g_z = 0.0
    x = np.linspace(-g_len / 2, g_len / 2, 2)
    y = np.linspace(-g_width / 2, g_width / 2, 2)
    X, Y = np.meshgrid(x, y)
    Z = np.full_like(X, g_z)
    ax.plot_surface(X, Y, Z, color="lightgray", alpha=0.5)


def setup_ax(ax, title, view_type="3d"):
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.set_zlabel("Z (m)")
    ax.set_title(title)
    ax.set_xlim(-5, 5)
    ax.set_ylim(-5, 5)
    ax.set_zlim(0, 4)
    ax.set_box_aspect([1, 1, 0.4])  # [x, y, z]

    if view_type == "top":
        ax.view_init(elev=90, azim=-90)
    elif view_type == "front":
        ax.view_init(elev=0, azim=0)
    elif view_type == "side":
        ax.view_init(elev=0, azim=-90)
    elif view_type == "3d":
        ax.view_init(elev=30, azim=-120)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true", help="Save the plot as an image")
    args = parser.parse_args()

    # --- SENSOR CONFIGURATION ---
    lidar_configs = [
        {"pos": [0.4, 0.25, 0.3], "rpy": [0, 14, 0], "name": "Main LiDAR"},
        {"pos": [-0.4, -0.25, 0.3], "rpy": [0, -14, 0], "name": "Front LiDAR"},
    ]

    camera_configs = [
        {"pos": [0.4, 0.0, 0.25], "rpy": [0, 30, 0], "name": "Front Camera"}
    ]

    uss_configs = [
        {"pos": [0.4, 0.1, 0.2], "rpy": [0, 0, 0], "name": "USS Front Right"},
        {"pos": [0.4, -0.1, 0.2], "rpy": [0, 0, 0], "name": "USS Front Left"},
        {"pos": [-0.4, 0.1, 0.2], "rpy": [0, 0, 180], "name": "USS Rear Right"},
        {"pos": [-0.4, -0.1, 0.2], "rpy": [0, 0, 180], "name": "USS Rear Left"},
        {"pos": [0.2, 0.2, 0.2], "rpy": [0, 0, 90], "name": "USS Side FR"},
        {"pos": [0.2, -0.2, 0.2], "rpy": [0, 0, -90], "name": "USS Side FL"},
        {"pos": [-0.2, 0.2, 0.2], "rpy": [0, 0, 90], "name": "USS Side RR"},
        {"pos": [-0.2, -0.2, 0.2], "rpy": [0, 0, -90], "name": "USS Side RL"},
    ]

    fig = plt.figure(figsize=(16, 12))

    views = [
        {"pos": 221, "title": "3D Perspective", "type": "3d"},
        {"pos": 222, "title": "Top View (XY Plane)", "type": "top"},
        {"pos": 223, "title": "Front View (YZ Plane)", "type": "front"},
        {"pos": 224, "title": "Side View (XZ Plane)", "type": "side"},
    ]

    axes = []
    for v in views:
        ax = fig.add_subplot(v["pos"], projection="3d")
        setup_ax(ax, v["title"], v["type"])

        plot_ground(ax)
        plot_vehicle(ax)

        for config in lidar_configs:
            plot_lidar_fov(ax, config["pos"], config["rpy"], name=config["name"])

        # for config in camera_configs:
        #     plot_camera_fov(ax, config["pos"], config["rpy"], name=config["name"])

        # for config in uss_configs:
        #     plot_uss_fov(ax, config["pos"], config["rpy"], name=config["name"])

        axes.append(ax)

    # Add legend to the figure instead of each ax to keep it clean
    handles = [
        plt.Line2D([0], [0], color="cyan", lw=4, label="LiDAR"),
        plt.Line2D([0], [0], color="lime", lw=4, label="Camera"),
        plt.Line2D([0], [0], color="yellow", lw=4, label="USS"),
        plt.Line2D([0], [0], color="gray", lw=4, label="Vehicle"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 0.98))

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    if args.save:
        plt.savefig("sensor_fov_multi_view.png", dpi=300)
        print("Visualization saved to sensor_fov_multi_view.png")
    else:
        plt.show()


if __name__ == "__main__":
    main()
