from sqlalchemy import Column, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geometry

Base = declarative_base()

class TimePoint(Base):
    __tablename__ = 'time_points'
    id = Column(Integer, primary_key=True)
    timestamp = Column(Integer, nullable=False, unique=True)

class SpatialGrid(Base):
    __tablename__ = 'spatial_grid'
    id = Column(Integer, primary_key=True)
    longitude = Column(Numeric, nullable=False)
    latitude = Column(Numeric, nullable=False)
    geom = Column(Geometry('POINT', srid=4326), nullable=False)

class SlpData(Base):
    __tablename__ = 'slp_data'
    id = Column(Integer, primary_key=True)
    time_id = Column(Integer, ForeignKey('time_points.id'), nullable=False)
    grid_id = Column(Integer, ForeignKey('spatial_grid.id'), nullable=False)
    pressure_value = Column(Numeric, nullable=False)

    time_point = relationship("TimePoint")
    spatial_grid = relationship("SpatialGrid")

    __table_args__ = (
        UniqueConstraint('time_id', 'grid_id', name='uix_time_grid'),
    )
