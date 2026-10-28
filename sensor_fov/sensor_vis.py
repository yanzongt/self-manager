from pathlib import Path

import numpy as np
import plotly.graph_objects as go


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


def create_grid_triangles(rows, cols):
    i, j, k = [], [], []
    for row in range(rows - 1):
        for col in range(cols - 1):
            p0 = row * cols + col
            p1 = p0 + 1
            p2 = p0 + cols
            p3 = p2 + 1
            i.extend([p0, p1])
            j.extend([p1, p3])
            k.extend([p2, p2])
    return i, j, k


def create_box_trace(vertices, name, color, opacity=1.0):
    return go.Mesh3d(
        x=vertices[:, 0],
        y=vertices[:, 1],
        z=vertices[:, 2],
        i=[0, 0, 0, 1, 2, 3, 4, 4, 4, 5, 6, 7],
        j=[1, 2, 4, 5, 6, 7, 5, 6, 0, 1, 2, 3],
        k=[2, 3, 5, 6, 7, 4, 6, 7, 1, 2, 3, 0],
        opacity=opacity,
        color=color,
        name=name,
    )


def create_box_edges(vertices, name, color="black", width=4):
    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ]
    edge_x, edge_y, edge_z = [], [], []
    for start_idx, end_idx in edges:
        edge_x.extend([vertices[start_idx, 0], vertices[end_idx, 0], None])
        edge_y.extend([vertices[start_idx, 1], vertices[end_idx, 1], None])
        edge_z.extend([vertices[start_idx, 2], vertices[end_idx, 2], None])
    return go.Scatter3d(
        x=edge_x,
        y=edge_y,
        z=edge_z,
        mode="lines",
        line=dict(color=color, width=width),
        name=name,
        showlegend=False,
        hoverinfo="skip",
    )


def order_xy_corners(corners):
    center = np.mean(corners[:, :2], axis=0)
    angles = np.arctan2(corners[:, 1] - center[1], corners[:, 0] - center[0])
    return corners[np.argsort(angles)]


def intersect_rays_with_ground(pos, rays, max_range, ground_z=0.0):
    pos = np.array(pos)
    dz = rays[:, 2]
    valid = np.abs(dz) > 1e-6
    t = np.full(rays.shape[0], np.nan)
    t[valid] = (ground_z - pos[2]) / dz[valid]
    valid = valid & (t >= 0.0) & (t <= max_range)
    points = pos + rays * t[:, None]
    return points[valid]


def create_ground_intersection_trace(
    pos,
    rpy,
    name,
    color="red",
    max_range=2.5,
    v_min=-7,
    v_max=52,
    ground_z=0.0,
    legendgroup="LiDAR",
):
    phi = np.linspace(0, 2 * np.pi, 240)
    elevations = np.linspace(np.radians(v_min), np.radians(v_max), 80)
    phi_grid, elev_grid = np.meshgrid(phi, elevations)

    local_rays = np.stack(
        [
            np.cos(elev_grid).ravel() * np.cos(phi_grid).ravel(),
            np.cos(elev_grid).ravel() * np.sin(phi_grid).ravel(),
            np.sin(elev_grid).ravel(),
        ],
        axis=1,
    )
    R = get_rotation_matrix(*rpy)
    world_rays = (R @ local_rays.T).T
    points = intersect_rays_with_ground(pos, world_rays, max_range, ground_z)

    hit_trace = go.Scatter3d(
        x=points[:, 0] if len(points) else [],
        y=points[:, 1] if len(points) else [],
        z=np.full(len(points), ground_z + 0.006) if len(points) else [],
        mode="markers",
        marker=dict(size=2.5, color=color, opacity=0.85),
        name=f"{name} ground hit",
        legendgroup=legendgroup,
        showlegend=True,
        hoverinfo="skip",
    )

    boundary_x, boundary_y, boundary_z = [], [], []
    for v_deg in [v_min, v_max]:
        elev = np.radians(v_deg)
        local_boundary = np.stack(
            [
                np.cos(elev) * np.cos(phi),
                np.cos(elev) * np.sin(phi),
                np.full_like(phi, np.sin(elev)),
            ],
            axis=1,
        )
        world_boundary = (R @ local_boundary.T).T
        for ray in world_boundary:
            point = intersect_rays_with_ground(pos, ray.reshape(1, 3), max_range, ground_z)
            if len(point) == 0:
                if boundary_x and boundary_x[-1] is not None:
                    boundary_x.append(None)
                    boundary_y.append(None)
                    boundary_z.append(None)
                continue
            boundary_x.append(point[0, 0])
            boundary_y.append(point[0, 1])
            boundary_z.append(ground_z + 0.012)
        if boundary_x and boundary_x[-1] is not None:
            boundary_x.append(None)
            boundary_y.append(None)
            boundary_z.append(None)

    boundary_trace = go.Scatter3d(
        x=boundary_x,
        y=boundary_y,
        z=boundary_z,
        mode="lines",
        line=dict(color=color, width=8),
        name=f"{name} ground boundary",
        legendgroup=legendgroup,
        showlegend=False,
        hoverinfo="skip",
    )

    return [hit_trace, boundary_trace]


def create_lidar_body(
    pos, rpy, name="LiDAR body", radius=0.035, color="darkblue", legendgroup="LiDAR"
):
    phi = np.linspace(0, 2 * np.pi, 40)
    theta = np.linspace(0, np.pi / 2, 12)
    phi_grid, theta_grid = np.meshgrid(phi, theta)

    x = radius * np.sin(theta_grid) * np.cos(phi_grid)
    y = radius * np.sin(theta_grid) * np.sin(phi_grid)
    z = radius * np.cos(theta_grid)

    points = np.vstack([x.ravel(), y.ravel(), z.ravel()]).T
    transformed = apply_transform(points, pos, *rpy)
    mesh_i, mesh_j, mesh_k = create_grid_triangles(theta_grid.shape[0], theta_grid.shape[1])

    mesh = go.Mesh3d(
        x=transformed[:, 0],
        y=transformed[:, 1],
        z=transformed[:, 2],
        i=mesh_i,
        j=mesh_j,
        k=mesh_k,
        opacity=1.0,
        color=color,
        name=name,
        legendgroup=legendgroup,
        showlegend=True,
    )

    base_points = np.vstack(
        [
            radius * np.cos(phi),
            radius * np.sin(phi),
            np.zeros_like(phi),
        ]
    ).T
    base = apply_transform(base_points, pos, *rpy)
    base_ring = go.Scatter3d(
        x=base[:, 0],
        y=base[:, 1],
        z=base[:, 2],
        mode="lines",
        line=dict(color="black", width=4),
        name=f"{name} base",
        legendgroup=legendgroup,
        showlegend=False,
        hoverinfo="skip",
    )

    return [mesh, base_ring]


def create_lidar_fov(
    pos, rpy, name="LiDAR", color="cyan", opacity=0.2, legendgroup="LiDAR"
):
    """
    FOV: 360 horizontal, -7 to 52 vertical.
    """
    r = 3  # Visualization radius
    v_min, v_max = -7, 52

    phi = np.linspace(0, 2 * np.pi, 80)
    theta = np.linspace(np.radians(90 - v_max), np.radians(90 - v_min), 16)
    phi_grid, theta_grid = np.meshgrid(phi, theta)

    x = r * np.sin(theta_grid) * np.cos(phi_grid)
    y = r * np.sin(theta_grid) * np.sin(phi_grid)
    z = r * np.cos(theta_grid)

    points = np.vstack([x.ravel(), y.ravel(), z.ravel()]).T
    transformed = apply_transform(points, pos, *rpy)

    tx = transformed[:, 0]
    ty = transformed[:, 1]
    tz = transformed[:, 2]
    mesh_i, mesh_j, mesh_k = create_grid_triangles(theta_grid.shape[0], theta_grid.shape[1])

    # Mesh for the FOV shell. Explicit triangles avoid Plotly auto-triangulation
    # getting stuck on this non-planar ring-like surface.
    mesh = go.Mesh3d(
        x=tx,
        y=ty,
        z=tz,
        i=mesh_i,
        j=mesh_j,
        k=mesh_k,
        opacity=opacity,
        color=color,
        name=name,
        legendgroup=legendgroup,
        showlegend=True,
    )

    # Wireframe lines (circles at top and bottom)
    traces = [mesh]
    for t in [np.radians(90 - v_min), np.radians(90 - v_max)]:
        circ_x = r * np.sin(t) * np.cos(phi)
        circ_y = r * np.sin(t) * np.sin(phi)
        circ_z = np.full_like(phi, r * np.cos(t))
        circ_pts = np.vstack([circ_x, circ_y, circ_z]).T
        t_circ = apply_transform(circ_pts, pos, *rpy)
        traces.append(
            go.Scatter3d(
                x=t_circ[:, 0],
                y=t_circ[:, 1],
                z=t_circ[:, 2],
                mode="lines",
                line=dict(color=color, width=2),
                legendgroup=legendgroup,
                showlegend=False,
                hoverinfo="skip",
            )
        )

    return traces


def create_camera_fov(
    pos, rpy, h_fov=86, v_fov=57, d=4.0, name="Camera", color="lime", opacity=0.3
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
    x, y, z = transformed.T

    # Mesh
    mesh = go.Mesh3d(
        x=x,
        y=y,
        z=z,
        i=[0, 0, 0, 0, 1, 1],
        j=[1, 2, 3, 4, 2, 3],
        k=[2, 3, 4, 1, 3, 4],
        opacity=opacity,
        color=color,
        name=name,
        legendgroup="Camera",
        showlegend=True,
    )

    # Wireframe
    edges = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (2, 3), (3, 4), (4, 1)]
    edge_x, edge_y, edge_z = [], [], []
    for start, end in edges:
        edge_x.extend([x[start], x[end], None])
        edge_y.extend([y[start], y[end], None])
        edge_z.extend([z[start], z[end], None])

    wireframe = go.Scatter3d(
        x=edge_x,
        y=edge_y,
        z=edge_z,
        mode="lines",
        line=dict(color=color, width=3),
        legendgroup="Camera",
        showlegend=False,
        hoverinfo="skip",
    )

    return [mesh, wireframe]


def create_uss_fov(
    pos, rpy, fov_deg=60, d=2.0, name="USS", color="yellow", opacity=0.4
):
    """
    FOV: Conical circular FOV.
    """
    angle_half = np.radians(fov_deg / 2)
    radius = d * np.tan(angle_half)

    v0 = [0, 0, 0]
    theta = np.linspace(0, 2 * np.pi, 24)
    circle_points = [[d, radius * np.cos(t), radius * np.sin(t)] for t in theta]

    vertices = np.array([v0] + circle_points)
    transformed = apply_transform(vertices, pos, *rpy)
    x, y, z = transformed.T

    # Mesh
    num_pts = len(circle_points)
    i = [0] * num_pts
    j = list(range(1, num_pts + 1))
    k = [(n % num_pts) + 1 for n in range(2, num_pts + 2)]

    mesh = go.Mesh3d(
        x=x,
        y=y,
        z=z,
        i=i,
        j=j,
        k=k,
        opacity=opacity,
        color=color,
        name=name,
        legendgroup="USS",
        showlegend=True,
    )

    # Wireframe (circle + 4 rays)
    edge_x, edge_y, edge_z = [], [], []
    # Circle
    edge_x.extend(np.append(x[1:], x[1]))
    edge_y.extend(np.append(y[1:], y[1]))
    edge_z.extend(np.append(z[1:], z[1]))
    edge_x.append(None)
    edge_y.append(None)
    edge_z.append(None)
    # Rays
    for idx in [1, 1 + num_pts // 4, 1 + num_pts // 2, 1 + 3 * num_pts // 4]:
        edge_x.extend([x[0], x[idx], None])
        edge_y.extend([y[0], y[idx], None])
        edge_z.extend([z[0], z[idx], None])

    wireframe = go.Scatter3d(
        x=edge_x,
        y=edge_y,
        z=edge_z,
        mode="lines",
        line=dict(color=color, width=2),
        legendgroup="USS",
        showlegend=False,
        hoverinfo="skip",
    )

    return [mesh, wireframe]


def create_ground_surface_trace(ground_size, ground_z):
    ground_x = np.linspace(-ground_size / 2, ground_size / 2, 2)
    ground_y = np.linspace(-ground_size / 2, ground_size / 2, 2)
    ground_x_grid, ground_y_grid = np.meshgrid(ground_x, ground_y)
    ground_z_grid = np.full_like(ground_x_grid, ground_z)
    return go.Surface(
        x=ground_x_grid,
        y=ground_y_grid,
        z=ground_z_grid,
        opacity=0.35,
        colorscale=[[0, "rgb(230,230,230)"], [1, "rgb(230,230,230)"]],
        showscale=False,
        name="ground",
        hoverinfo="skip",
    )


def create_ground_grid_trace(ground_size, ground_z):
    grid_lines = np.linspace(-ground_size / 2, ground_size / 2, 11)
    grid_x, grid_y, grid_z = [], [], []
    for value in grid_lines:
        grid_x.extend([-ground_size / 2, ground_size / 2, None, value, value, None])
        grid_y.extend([value, value, None, -ground_size / 2, ground_size / 2, None])
        grid_z.extend(
            [
                ground_z + 0.003,
                ground_z + 0.003,
                None,
                ground_z + 0.003,
                ground_z + 0.003,
                None,
            ]
        )
    return go.Scatter3d(
        x=grid_x,
        y=grid_y,
        z=grid_z,
        mode="lines",
        line=dict(color="rgb(150,150,150)", width=1),
        name="ground grid",
        showlegend=False,
        hoverinfo="skip",
    )


def make_ground_slider_steps(
    ground_heights, ground_size, lidar_configs, dynamic_trace_indices
):
    steps = []
    for ground_z in ground_heights:
        ground_surface = create_ground_surface_trace(ground_size, ground_z)
        ground_grid = create_ground_grid_trace(ground_size, ground_z)

        trace_indices = [
            dynamic_trace_indices["ground"],
            dynamic_trace_indices["ground_grid"],
        ]
        update = {
            "x": [ground_surface.x, ground_grid.x],
            "y": [ground_surface.y, ground_grid.y],
            "z": [ground_surface.z, ground_grid.z],
        }

        for config, hit_idx, boundary_idx in dynamic_trace_indices["lidar_ground"]:
            hit_trace, boundary_trace = create_ground_intersection_trace(
                config["pos"], config["rpy"], name=config["name"], color="red", ground_z=ground_z
            )
            trace_indices.extend([hit_idx, boundary_idx])
            update["x"].extend([hit_trace.x, boundary_trace.x])
            update["y"].extend([hit_trace.y, boundary_trace.y])
            update["z"].extend([hit_trace.z, boundary_trace.z])

        steps.append(
            dict(
                label=f"{ground_z:.2f} m",
                method="update",
                args=[
                    update,
                    {"scene.zaxis.range": [min(-0.05, ground_z - 0.1), 4]},
                    trace_indices,
                ],
            )
        )
    return steps


def main():
    # --- SENSOR CONFIGURATION ---
    # format: (x, y, z, roll, pitch, yaw)

    # 2 LiDARs
    lidar_configs = [
        # 这里的高度添加上了25mm的离地间隙.
        {"pos": [-0.161, -0.117, 0.244], "rpy": [0, -15, 0], "name": "Back LiDAR"},
        {"pos": [0.265, 0.0, 0.298], "rpy": [0, 15, 0], "name": "Front LiDAR"},
    ]

    # 1 Camera
    camera_configs = [
        # {"pos": [0.4, 0.0, 0.25], "rpy": [0, 30, 0], "name": "Front Camera"}
    ]

    # 8 USS sensors
    uss_configs = [
        # {"pos": [0.4, 0.1, 0.2], "rpy": [0, 0, 0], "name": "USS Front Right"},
        # {"pos": [0.4, -0.1, 0.2], "rpy": [0, 0, 0], "name": "USS Front Left"},
        # {"pos": [-0.4, 0.1, 0.2], "rpy": [0, 0, 180], "name": "USS Rear Right"},
        # {"pos": [-0.4, -0.1, 0.2], "rpy": [0, 0, 180], "name": "USS Rear Left"},
        # {"pos": [0.2, 0.2, 0.2], "rpy": [0, 0, 90], "name": "USS Side FR"},
        # {"pos": [0.2, -0.2, 0.2], "rpy": [0, 0, -90], "name": "USS Side FL"},
        # {"pos": [-0.2, 0.2, 0.2], "rpy": [0, 0, 90], "name": "USS Side RR"},
        # {"pos": [-0.2, -0.2, 0.2], "rpy": [0, 0, -90], "name": "USS Side RL"},
    ]

    fig = go.Figure()
    ground_heights = [0.0, 0.03, 0.1, 0.15, 0.2, 0.5, 1.0, 2.0]
    initial_ground_z = ground_heights[0]
    dynamic_trace_indices = {"lidar_ground": []}
    lidar_legendgroups = []

    # Add LiDARs
    for lidar_index, config in enumerate(lidar_configs):
        # Each LiDAR uses its own legend group so its FOV can be toggled
        # independently from the other LiDARs in the generated HTML.
        legendgroup = f"lidar-{lidar_index}"
        lidar_legendgroups.append((config["name"], legendgroup))
        fig.add_traces(
            create_lidar_body(
                config["pos"],
                config["rpy"],
                name=f"{config['name']} body",
                legendgroup=legendgroup,
            )
        )
        fig.add_traces(
            create_lidar_fov(
                config["pos"],
                config["rpy"],
                name=config["name"],
                legendgroup=legendgroup,
            )
        )
        ground_traces = create_ground_intersection_trace(
            config["pos"],
            config["rpy"],
            name=config["name"],
            color="red",
            ground_z=initial_ground_z,
            legendgroup=legendgroup,
        )
        hit_idx = len(fig.data)
        fig.add_traces(ground_traces)
        dynamic_trace_indices["lidar_ground"].append((config, hit_idx, hit_idx + 1))

    # Add Camera
    for config in camera_configs:
        fig.add_traces(
            create_camera_fov(config["pos"], config["rpy"], name=config["name"])
        )

    # Add USS
    for config in uss_configs:
        fig.add_traces(
            create_uss_fov(config["pos"], config["rpy"], name=config["name"])
        )

    # Add a configurable box for the vehicle body.
    # Bottom corners are relative to the bottom-center point. Configure the 4
    # corners in clockwise or counter-clockwise order. The box is extruded along +Z.
    vehicle_bottom_center = np.array([0.0, 0.0, 0.0])
    vehicle_height = 0.2
    vehicle_bottom_corners = np.array(
        [
            [0.323, 0.27, 0.0],
            [0.323, -0.27, 0.0],
            [-0.261, -0.27, 0.0],
            [-0.261, 0.27, 0.0],
        ]
    )
    vehicle_bottom_corners = order_xy_corners(vehicle_bottom_corners)
    vehicle_bottom_corners[:, 2] = 0.0
    vehicle_bottom_vertices = vehicle_bottom_center + vehicle_bottom_corners
    vehicle_top_vertices = vehicle_bottom_vertices + np.array([0.0, 0.0, vehicle_height])
    vehicle_vertices = np.vstack([vehicle_bottom_vertices, vehicle_top_vertices])
    fig.add_trace(create_box_trace(vehicle_vertices, name="Vehicle", color="gray"))
    fig.add_trace(create_box_edges(vehicle_vertices, name="Vehicle edges"))

    ground_size = 10.0
    dynamic_trace_indices["ground"] = len(fig.data)
    fig.add_trace(create_ground_surface_trace(ground_size, initial_ground_z))
    dynamic_trace_indices["ground_grid"] = len(fig.data)
    fig.add_trace(create_ground_grid_trace(ground_size, initial_ground_z))

    # Keep the vehicle and ground visible when selecting one sensor category.
    always_visible_trace_names = {"Vehicle", "Vehicle edges", "ground", "ground grid"}

    def visible_for_legendgroups(*legendgroups):
        return [
            trace.legendgroup in legendgroups or trace.name in always_visible_trace_names
            for trace in fig.data
        ]

    sensor_buttons = [
        dict(
            label="All",
            method="update",
            args=[{"visible": [True] * len(fig.data)}],
        ),
        dict(
            label="Only LiDAR",
            method="update",
            args=[{"visible": visible_for_legendgroups(*(group for _, group in lidar_legendgroups))}],
        ),
    ]
    sensor_buttons.extend(
        dict(
            label=f"Only {name}",
            method="update",
            args=[{"visible": visible_for_legendgroups(legendgroup)}],
        )
        for name, legendgroup in lidar_legendgroups
    )
    sensor_buttons.extend(
        [
            dict(
                label="Only Camera",
                method="update",
                args=[{"visible": visible_for_legendgroups("Camera")}],
            ),
            dict(
                label="Only USS",
                method="update",
                args=[{"visible": visible_for_legendgroups("USS")}],
            ),
        ]
    )

    # Set layout with UI buttons
    fig.update_layout(
        title="Sensor FOV Visualization (Click legend or buttons to toggle)",
        scene=dict(
            xaxis=dict(nticks=10, range=[-5, 5]),
            yaxis=dict(nticks=10, range=[-5, 5]),
            zaxis=dict(nticks=10, range=[0, 4]),
            aspectmode="data",
        ),
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=0.1,
                y=1.1,
                buttons=sensor_buttons,
            ),
            dict(
                type="buttons",
                direction="right",
                x=0.62,
                y=1.1,
                buttons=list(
                    [
                        dict(
                            label="XY View",
                            method="relayout",
                            args=[
                                {
                                    "scene.camera": dict(
                                        eye=dict(x=0, y=0, z=2.5),
                                        up=dict(x=0, y=1, z=0),
                                        center=dict(x=0, y=0, z=0),
                                    )
                                }
                            ],
                        ),
                        dict(
                            label="3D View",
                            method="relayout",
                            args=[
                                {
                                    "scene.camera": dict(
                                        eye=dict(x=1.6, y=1.6, z=1.1),
                                        up=dict(x=0, y=0, z=1),
                                        center=dict(x=0, y=0, z=0),
                                    )
                                }
                            ],
                        ),
                    ]
                ),
            ),
        ],
        sliders=[
            dict(
                active=0,
                currentvalue=dict(prefix="Ground Z: ", suffix=""),
                pad=dict(t=45),
                steps=make_ground_slider_steps(
                    ground_heights, ground_size, lidar_configs, dynamic_trace_indices
                ),
            )
        ],
        margin=dict(l=0, r=0, b=0, t=60),
    )

    # Save as a standalone HTML file. Open it manually in a browser if needed.
    output_path = Path("sensor_fov_vis.html").resolve()
    fig.write_html(
        str(output_path),
        include_plotlyjs=True,
        full_html=True,
        auto_open=False,
    )
    print(f"Visualization saved to {output_path}")


if __name__ == "__main__":
    main()
