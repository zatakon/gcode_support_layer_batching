"""G-code parser for multi-material 3D printing.

This module provides functionality to parse G-code files, identify layers,
tool changes, and extract geometric information for collision detection.
"""

import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np


@dataclass
class GCodeCommand:
    """Represents a single G-code command."""
    line_number: int
    raw_line: str
    command: str
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    e: Optional[float] = None
    f: Optional[float] = None
    tool: Optional[int] = None
    comment: Optional[str] = None


@dataclass
class Layer:
    """Represents a single print layer."""
    layer_number: int
    z_height: float
    commands: List[GCodeCommand] = field(default_factory=list)
    tool: Optional[int] = None
    bounds: Optional[Tuple[float, float, float, float]] = None  # (min_x, min_y, max_x, max_y)
    
    def calculate_bounds(self) -> Tuple[float, float, float, float]:
        """Calculate the bounding box of this layer."""
        x_coords = [cmd.x for cmd in self.commands if cmd.x is not None]
        y_coords = [cmd.y for cmd in self.commands if cmd.y is not None]
        
        if not x_coords or not y_coords:
            return (0, 0, 0, 0)
        
        self.bounds = (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
        return self.bounds


class GCodeParser:
    """Parser for G-code files with multi-material support."""
    
    def __init__(self):
        self.layers: List[Layer] = []
        self.current_tool: Optional[int] = None
        self.current_position = {'x': 0.0, 'y': 0.0, 'z': 0.0, 'e': 0.0}
        
    def parse_file(self, filepath: str) -> List[Layer]:
        """Parse a G-code file and return a list of layers."""
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        return self.parse_lines(lines)
    
    def parse_lines(self, lines: List[str]) -> List[Layer]:
        """Parse G-code lines and organize into layers."""
        current_layer: Optional[Layer] = None
        current_z: Optional[float] = None
        layer_number = 0
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith(';'):
                continue
            
            cmd = self._parse_command(line_num, line)
            
            # Track tool changes
            if cmd.command and cmd.command.startswith('T'):
                try:
                    self.current_tool = int(cmd.command[1:])
                    cmd.tool = self.current_tool
                except ValueError:
                    pass
            
            # Track position
            if cmd.x is not None:
                self.current_position['x'] = cmd.x
            if cmd.y is not None:
                self.current_position['y'] = cmd.y
            if cmd.z is not None:
                self.current_position['z'] = cmd.z
            if cmd.e is not None:
                self.current_position['e'] = cmd.e
            
            # Detect layer changes (Z movement)
            if cmd.z is not None and (current_z is None or cmd.z > current_z):
                # New layer detected
                if current_layer is not None:
                    current_layer.calculate_bounds()
                    self.layers.append(current_layer)
                
                current_z = cmd.z
                layer_number += 1
                current_layer = Layer(
                    layer_number=layer_number,
                    z_height=current_z,
                    tool=self.current_tool
                )
            
            # Add command to current layer
            if current_layer is not None:
                current_layer.commands.append(cmd)
                # Update layer tool if it changes within the layer
                if cmd.tool is not None:
                    current_layer.tool = cmd.tool
        
        # Add the last layer
        if current_layer is not None:
            current_layer.calculate_bounds()
            self.layers.append(current_layer)
        
        return self.layers
    
    def _parse_command(self, line_number: int, line: str) -> GCodeCommand:
        """Parse a single G-code command line."""
        # Remove comments
        comment = None
        if ';' in line:
            line, comment = line.split(';', 1)
            line = line.strip()
            comment = comment.strip()
        
        # Extract command
        parts = line.split()
        if not parts:
            return GCodeCommand(line_number=line_number, raw_line=line, command='')
        
        command = parts[0]
        
        # Parse parameters
        x = self._extract_float(line, 'X')
        y = self._extract_float(line, 'Y')
        z = self._extract_float(line, 'Z')
        e = self._extract_float(line, 'E')
        f = self._extract_float(line, 'F')
        
        return GCodeCommand(
            line_number=line_number,
            raw_line=line,
            command=command,
            x=x, y=y, z=z, e=e, f=f,
            comment=comment
        )
    
    def _extract_float(self, line: str, param: str) -> Optional[float]:
        """Extract a float parameter from a G-code line."""
        pattern = rf'{param}([-+]?\d*\.?\d+)'
        match = re.search(pattern, line)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None
    
    def get_tool_changes(self) -> List[Tuple[int, int]]:
        """Return a list of (layer_number, tool) for each tool change."""
        changes = []
        prev_tool = None
        
        for layer in self.layers:
            if layer.tool != prev_tool:
                changes.append((layer.layer_number, layer.tool))
                prev_tool = layer.tool
        
        return changes
    
    def get_layers_by_tool(self, tool: int) -> List[Layer]:
        """Get all layers printed with a specific tool."""
        return [layer for layer in self.layers if layer.tool == tool]
