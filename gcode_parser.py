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
    is_tool_change_sequence: bool = False  # Marks commands part of tool change


@dataclass
class ObjectSegment:
    """Represents a segment of one object within a layer."""
    object_id: Optional[str] = None  # Object label id from M624 command
    tool: Optional[int] = None
    commands: List[GCodeCommand] = field(default_factory=list)
    tool_change_commands: List[GCodeCommand] = field(default_factory=list)
    bounds: Optional[Tuple[float, float, float, float]] = None
    
    def calculate_bounds(self) -> Tuple[float, float, float, float]:
        """Calculate the bounding box of this segment."""
        x_coords = [cmd.x for cmd in self.commands if cmd.x is not None]
        y_coords = [cmd.y for cmd in self.commands if cmd.y is not None]
        
        if not x_coords or not y_coords:
            return (0, 0, 0, 0)
        
        self.bounds = (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
        return self.bounds


@dataclass
class Layer:
    """Represents a single print layer, potentially containing multiple objects."""
    layer_number: int
    z_height: float
    segments: List[ObjectSegment] = field(default_factory=list)  # Multiple objects in this layer
    commands: List[GCodeCommand] = field(default_factory=list)  # Layer-level commands (deprecated, use segments)
    tool: Optional[int] = None  # Deprecated, use segments instead
    bounds: Optional[Tuple[float, float, float, float]] = None
    tool_change_commands: List[GCodeCommand] = field(default_factory=list)
    
    def calculate_bounds(self) -> Tuple[float, float, float, float]:
        """Calculate the bounding box of this layer (all segments)."""
        all_x = []
        all_y = []
        for segment in self.segments:
            x_coords = [cmd.x for cmd in segment.commands if cmd.x is not None]
            y_coords = [cmd.y for cmd in segment.commands if cmd.y is not None]
            all_x.extend(x_coords)
            all_y.extend(y_coords)
        
        if not all_x or not all_y:
            return (0, 0, 0, 0)
        
        self.bounds = (min(all_x), min(all_y), max(all_x), max(all_y))
        return self.bounds


class GCodeParser:
    """Parser for G-code files with multi-material support."""
    
    def __init__(self):
        self.layers: List[Layer] = []
        self.current_tool: Optional[int] = None
        self.current_position = {'x': 0.0, 'y': 0.0, 'z': 0.0, 'e': 0.0}
        self.pending_tool_change_commands: List[GCodeCommand] = []
        self.in_tool_change_sequence: bool = False
        self.header_lines: List[str] = []  # Store header and config blocks
    
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
        in_header = True
        
        for line_num, line in enumerate(lines):
            original_line = line
            line = line.strip()
            if not line:
                if in_header:
                    self.header_lines.append(original_line)
                continue
            
            # Check for layer markers in comments (e.g., OrcaSlicer format)
            if line.startswith(';') and 'layer num/total_layer_count:' in line.lower():
                # Layer markers have format: "; layer num/total_layer_count: 1/128"
                # Config lines have format: "; layer_change_gcode = ... layer num/total_layer_count: ..."
                # Only treat as layer marker if it's a direct comment (not a config value with '=')
                if '=' not in line or line.index(':') < line.index('='):
                    # This is an actual layer marker - stop capturing header
                    in_header = False
                    # Extract layer number from comment
                    match = re.search(r'layer num/total_layer_count:\s*(\d+)/(\d+)', line, re.IGNORECASE)
                    if match:
                        # Save current layer if it exists
                        if current_layer is not None:
                            current_layer.calculate_bounds()
                            self.layers.append(current_layer)
                        
                        # Start new layer
                        layer_number = int(match.group(1))
                        current_layer = Layer(
                            layer_number=layer_number,
                            z_height=current_z if current_z is not None else 0.0,
                            tool=self.current_tool if self.current_tool is not None else 0,
                            tool_change_commands=self.pending_tool_change_commands.copy()
                        )
                        # Clear pending tool change commands and end sequence
                        self.pending_tool_change_commands.clear()
                        self.in_tool_change_sequence = False
                    continue
            
            # Capture header and config blocks (everything before first layer marker)
            if in_header:
                self.header_lines.append(original_line)
                continue
            
            cmd = self._parse_command(line_num, line)
            
            # Track tool changes (only T0-T9, ignore special commands like T1000)
            if cmd.command and cmd.command.startswith('T'):
                try:
                    tool_num = int(cmd.command[1:])
                    # Only accept tool numbers 0-9 (standard extruders)
                    if 0 <= tool_num <= 9:
                        self.current_tool = tool_num
                        cmd.tool = self.current_tool
                        cmd.is_tool_change_sequence = True
                        self.in_tool_change_sequence = True
                except ValueError:
                    pass
            
            # Capture tool change sequence commands
            if self.in_tool_change_sequence:
                cmd.is_tool_change_sequence = True
                self.pending_tool_change_commands.append(cmd)
            
            # Track position
            if cmd.x is not None:
                self.current_position['x'] = cmd.x
            if cmd.y is not None:
                self.current_position['y'] = cmd.y
            if cmd.z is not None:
                self.current_position['z'] = cmd.z
                # Update current Z height for layer tracking
                if cmd.z > (current_z or 0):
                    current_z = cmd.z
                    # Update current layer's z_height if layer exists
                    if current_layer is not None:
                        current_layer.z_height = current_z
            if cmd.e is not None:
                self.current_position['e'] = cmd.e
            
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
