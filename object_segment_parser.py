"""Parse G-code into object segments for multi-object batching.

This module extends the basic parser to split physical layers into
per-object segments that can be batched independently.
"""

from typing import List, Optional
from dataclasses import dataclass, field
from gcode_parser import GCodeParser, GCodeCommand, Layer


@dataclass
class ObjectLayer:
    """Represents one object's contribution to a physical layer."""
    layer_number: int  # Physical layer number
    object_id: Optional[str] = None  # Object label ID
    tool: int = 0
    z_height: float = 0.0
    commands: List[GCodeCommand] = field(default_factory=list)
    tool_change_commands: List[GCodeCommand] = field(default_factory=list)
    
    def __repr__(self):
        return f"ObjectLayer(layer={self.layer_number}, obj={self.object_id}, tool={self.tool}, cmds={len(self.commands)})"


class ObjectSegmentParser:
    """Parse G-code and split into per-object layers."""
    
    def __init__(self):
        self.base_parser = GCodeParser()
    
    def parse_file(self, filepath: str) -> List[ObjectLayer]:
        """Parse G-code file and split into object layers.
        
        Each physical layer that contains multiple objects will be split
        into multiple ObjectLayer instances, one per object.
        
        Args:
            filepath: Path to G-code file
            
        Returns:
            List of ObjectLayer instances, split by object
        """
        # First parse normally
        physical_layers = self.base_parser.parse_file(filepath)
        
        # Then split each physical layer into object segments
        object_layers = []
        
        for layer in physical_layers:
            # Split this layer by tool changes
            segments = self._split_layer_by_tool_change(layer)
            object_layers.extend(segments)
        
        return object_layers
    
    def _split_layer_by_tool_change(self, layer: Layer) -> List[ObjectLayer]:
        """Split a physical layer into object segments.
        
        Args:
            layer: Physical layer to split
            
        Returns:
            List of ObjectLayer instances (one per object in the layer)
        """
        segments = []
        current_commands = []
        current_tool = None
        tool_change_commands = []
        in_tool_change = False
        
        # Determine the starting tool for this layer
        # If there are tool_change_commands, use the last one's tool
        if layer.tool_change_commands:
            for cmd in layer.tool_change_commands:
                if cmd.command and cmd.command.startswith('T'):
                    try:
                        tool_num = int(cmd.command[1:])
                        if 0 <= tool_num <= 9:
                            current_tool = tool_num
                    except ValueError:
                        pass
        
        # If no starting tool found, default to 0
        if current_tool is None:
            current_tool = 0
        
        for cmd in layer.commands:
            # Detect tool change
            if cmd.command and cmd.command.startswith('T'):
                try:
                    tool_num = int(cmd.command[1:])
                    if 0 <= tool_num <= 9:
                        # Save current segment before tool change
                        if current_commands:
                            seg = ObjectLayer(
                                layer_number=layer.layer_number,
                                tool=current_tool,
                                z_height=layer.z_height,
                                commands=current_commands,
                                tool_change_commands=tool_change_commands.copy()
                            )
                            segments.append(seg)
                            current_commands = []
                            tool_change_commands = []
                        
                        # Start new segment with new tool
                        current_tool = tool_num
                        in_tool_change = True
                        tool_change_commands.append(cmd)
                        continue
                except ValueError:
                    pass
            
            # Collect tool change sequence commands
            if in_tool_change and (cmd.is_tool_change_sequence or 
                                   cmd.command in ['M620', 'M621', 'M104', 'M109', 'M106']):
                tool_change_commands.append(cmd)
                # End tool change after a certain point (when we see movement or extrusion)
                if cmd.x is not None or cmd.y is not None:
                    in_tool_change = False
            else:
                in_tool_change = False
                current_commands.append(cmd)
        
        # Add final segment
        if current_commands:
            seg = ObjectLayer(
                layer_number=layer.layer_number,
                tool=current_tool,
                z_height=layer.z_height,
                commands=current_commands,
                tool_change_commands=tool_change_commands.copy()
            )
            segments.append(seg)
        
        return segments if segments else [ObjectLayer(
            layer_number=layer.layer_number,
            tool=current_tool or 0,
            z_height=layer.z_height,
            commands=layer.commands,
            tool_change_commands=layer.tool_change_commands
        )]
    
    def get_header_lines(self) -> List[str]:
        """Get header lines from base parser."""
        return self.base_parser.header_lines
