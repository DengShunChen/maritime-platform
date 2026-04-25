CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS time_points (
    id SERIAL PRIMARY KEY,
    timestamp INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS spatial_grid (
    id SERIAL PRIMARY KEY,
    longitude NUMERIC NOT NULL,
    latitude NUMERIC NOT NULL,
    geom GEOMETRY(Point, 4326) NOT NULL,
    UNIQUE(longitude, latitude)
);

CREATE TABLE IF NOT EXISTS slp_data (
    id SERIAL PRIMARY KEY,
    time_id INTEGER NOT NULL REFERENCES time_points(id) ON DELETE CASCADE,
    grid_id INTEGER NOT NULL REFERENCES spatial_grid(id) ON DELETE CASCADE,
    pressure_value NUMERIC NOT NULL,
    UNIQUE(time_id, grid_id)
);
