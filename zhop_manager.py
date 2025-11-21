"""Z-hop manager for safe travel moves over printed geometry.

This module handles insertion of Z-hop moves when the nozzle needs to
travel over already-printed layers.
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass
from gcode_parser import GCodeCommand, Layer


@dataclass
class ZHopConfig:
    """Configuration for Z-hop behavior."""
    zhop_height: float = 0.5  # Z-hop height in mm
    zhop_speed: float = 10.0  # Z-hop movement speed in mm/s
    travel_speed: float = 150.0  # XY travel speed in mm/s
    enabled: bool = True
    
    def zhop_feedrate(self) -> float:
        """Return Z-hop feedrate in mm/min."""
        return self.zhop_speed * 60
    
    def travel_feedrate(self) -> float:
        """Return travel feedrate in mm/min."""
        return self.travel_speed * 60


class ZHopManager:
    """Manages Z-hop insertion for safe travel moves."""
    
    def __init__(self, config: ZHopConfig):
        """
        Initialize Z-hop manager.
        
        Args:
            config: Z-hop configuration
        """
        self.config = config
        self.current_z: Optional[float] = None
        self.is_hopped: bool = False
    
    def insert_zhop_for_travel(self, commands: List[GCodeCommand],
                              from_z: float, to_z: float,
                              current_pos: Tuple[float, float, float]) -> List[GCodeCommand]:
        """Insert Z-hop moves for travel between layers.
        
        Args:
            commands: List of G-code commands for the travel
            from_z: Starting Z height
            to_z: Destination Z height
            current_pos: Current (X, Y, Z) position
            
        Returns:
            Modified list of commands with Z-hop inserted
        """
        if not self.config.enabled:
            return commands
        
        # If moving to a lower layer, we need Z-hop
        if to_z < from_z:
            return self._add_zhop_sequence(commands, from_z, to_z, current_pos)
        
        return commands
    
    def _add_zhop_sequence(self, commands: List[GCodeCommand],
                          from_z: float, to_z: float,
                          current_pos: Tuple[float, float, float]) -> List[GCodeCommand]:
        """Add Z-hop up, travel, and Z-hop down sequence.
        
        Args:
            commands: Original commands
            from_z: Starting Z height
            to_z: Destination Z height
            current_pos: Current position
            
        Returns:
            Commands with Z-hop sequence
        """
        result = []
        x, y, z = current_pos
        
        # 1. Z-hop up
        zhop_z = from_z + self.config.zhop_height
        zhop_up = GCodeCommand(
            line_number=-1,
            raw_line=f"G1 Z{zhop_z:.3f} F{self.config.zhop_feedrate():.0f}",
            command="G1",
            z=zhop_z,
            f=self.config.zhop_feedrate(),
            comment="Z-hop up for layer travel"
        )
        result.append(zhop_up)
        
        # 2. Original travel moves (XY only, at safe Z height)
        for cmd in commands:
            if cmd.command in ['G0', 'G1'] and (cmd.x is not None or cmd.y is not None):
                # Travel at hopped height
                travel_cmd = GCodeCommand(
                    line_number=cmd.line_number,
                    raw_line=cmd.raw_line,
                    command=cmd.command,
                    x=cmd.x,
                    y=cmd.y,
                    z=None,  # Don't change Z during travel
                    f=self.config.travel_feedrate(),
                    comment="Travel at Z-hop height"
                )
                result.append(travel_cmd)
        
        # 3. Z-hop down to destination layer
        zhop_down = GCodeCommand(
            line_number=-1,
            raw_line=f"G1 Z{to_z:.3f} F{self.config.zhop_feedrate():.0f}",
            command="G1",
            z=to_z,
            f=self.config.zhop_feedrate(),
            comment="Z-hop down to destination layer"
        )
        result.append(zhop_down)
        
        return result
    
    def needs_zhop(self, from_layer: int, to_layer: int) -> bool:
        """Determine if Z-hop is needed for a layer transition.
        
        Args:
            from_layer: Starting layer number
            to_layer: Destination layer number
            
        Returns:
            True if Z-hop is needed
        """
        # Z-hop needed when moving to a layer that was already printed
        return to_layer < from_layer
