"""Prime tower management for multi-material printing.

This module manages separate prime towers for each material/tool,
ensuring proper synchronization and extrusion quality.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from gcode_parser import GCodeCommand, Layer


@dataclass
class PrimeTowerConfig:
    """Configuration for prime tower generation."""
    enabled: bool = True
    tower_size: float = 10.0  # mm per side
    tower_spacing: float = 5.0  # mm between towers
    wall_thickness: float = 0.8  # mm
    purge_volume: float = 30.0  # mm^3 to purge per tool change
    position_x: float = 200.0  # X position for first tower
    position_y: float = 200.0  # Y position for all towers
    layer_height: float = 0.2  # mm
    extrusion_width: float = 0.4  # mm


@dataclass
class PrimeTower:
    """Represents a prime tower for a specific tool."""
    tool: int
    position: Tuple[float, float]  # (X, Y) position
    size: float
    current_layer: int = 0
    
    def get_perimeter_commands(self, z_height: float, 
                              extrusion_width: float,
                              layer_height: float) -> List[GCodeCommand]:
        """Generate G-code commands to print the tower perimeter.
        
        Args:
            z_height: Z height for this layer
            extrusion_width: Extrusion width in mm
            layer_height: Layer height in mm
            
        Returns:
            List of G-code commands for the perimeter
        """
        commands = []
        x, y = self.position
        
        # Calculate extrusion amount for each side
        perimeter_length = self.size * 4
        side_length = self.size
        
        # Simplified extrusion calculation (volume / cross-section)
        extrusion_per_mm = (extrusion_width * layer_height) / 2.4  # Simplified
        e_per_side = side_length * extrusion_per_mm
        
        # Move to start position (bottom-left corner)
        move_cmd = GCodeCommand(
            line_number=-1,
            raw_line=f"G1 X{x:.3f} Y{y:.3f} F3000",
            command="G1",
            x=x, y=y, f=3000.0,
            comment=f"Move to T{self.tool} prime tower"
        )
        commands.append(move_cmd)
        
        # Draw square perimeter (counter-clockwise)
        corners = [
            (x + self.size, y),  # Right
            (x + self.size, y + self.size),  # Top-right
            (x, y + self.size),  # Top-left
            (x, y),  # Back to start
        ]
        
        for corner_x, corner_y in corners:
            extrude_cmd = GCodeCommand(
                line_number=-1,
                raw_line=f"G1 X{corner_x:.3f} Y{corner_y:.3f} E{e_per_side:.4f}",
                command="G1",
                x=corner_x, y=corner_y, e=e_per_side,
                comment="Prime tower perimeter"
            )
            commands.append(extrude_cmd)
        
        return commands


class PrimeTowerManager:
    """Manages multiple prime towers for multi-material printing."""
    
    def __init__(self, config: PrimeTowerConfig, num_tools: int):
        """
        Initialize prime tower manager.
        
        Args:
            config: Prime tower configuration
            num_tools: Number of tools/materials in the print
        """
        self.config = config
        self.towers: Dict[int, PrimeTower] = {}
        self._create_towers(num_tools)
    
    def _create_towers(self, num_tools: int) -> None:
        """Create prime towers for each tool."""
        for tool_id in range(num_tools):
            # Position towers side by side
            x_offset = tool_id * (self.config.tower_size + self.config.tower_spacing)
            position = (
                self.config.position_x + x_offset,
                self.config.position_y
            )
            
            tower = PrimeTower(
                tool=tool_id,
                position=position,
                size=self.config.tower_size
            )
            self.towers[tool_id] = tower
    
    def generate_tower_for_layer(self, tool: int, z_height: float, 
                                 layer_number: int) -> List[GCodeCommand]:
        """Generate prime tower commands for a specific tool and layer.
        
        Args:
            tool: Tool number
            z_height: Z height for this layer
            layer_number: Layer number
            
        Returns:
            List of G-code commands for the prime tower
        """
        if not self.config.enabled:
            return []
        
        if tool not in self.towers:
            return []
        
        tower = self.towers[tool]
        tower.current_layer = layer_number
        
        commands = tower.get_perimeter_commands(
            z_height,
            self.config.extrusion_width,
            self.config.layer_height
        )
        
        return commands
    
    def synchronize_towers(self, current_tool: int, 
                          current_layer: int,
                          z_height: float) -> List[GCodeCommand]:
        """Generate commands to synchronize all towers to current layer.
        
        This ensures all towers stay at the same height even when
        layers are batched.
        
        Args:
            current_tool: Currently active tool
            current_layer: Current layer number
            z_height: Current Z height
            
        Returns:
            List of G-code commands to print missing tower layers
        """
        commands = []
        
        for tool_id, tower in self.towers.items():
            # Skip current tool (it will print its tower anyway)
            if tool_id == current_tool:
                continue
            
            # Check if this tower is behind
            layers_behind = current_layer - tower.current_layer
            if layers_behind > 0:
                # Need to catch up this tower
                for layer_offset in range(layers_behind):
                    layer_z = z_height - (layers_behind - layer_offset - 1) * self.config.layer_height
                    layer_num = tower.current_layer + layer_offset + 1
                    
                    # Switch to this tool
                    tool_change = GCodeCommand(
                        line_number=-1,
                        raw_line=f"T{tool_id}",
                        command=f"T{tool_id}",
                        tool=tool_id,
                        comment=f"Switch to T{tool_id} for tower sync"
                    )
                    commands.append(tool_change)
                    
                    # Print tower layer
                    tower_cmds = self.generate_tower_for_layer(tool_id, layer_z, layer_num)
                    commands.extend(tower_cmds)
                    
                    # Retract after tower
                    retract = GCodeCommand(
                        line_number=-1,
                        raw_line="G1 E-1.0 F1800",
                        command="G1",
                        e=-1.0, f=1800.0,
                        comment="Retract after tower"
                    )
                    commands.append(retract)
        
        # Switch back to current tool
        if commands:
            tool_change_back = GCodeCommand(
                line_number=-1,
                raw_line=f"T{current_tool}",
                command=f"T{current_tool}",
                tool=current_tool,
                comment=f"Switch back to T{current_tool}"
            )
            commands.append(tool_change_back)
        
        return commands
    
    def get_tower_positions(self) -> Dict[int, Tuple[float, float]]:
        """Get the positions of all prime towers.
        
        Returns:
            Dictionary mapping tool number to (X, Y) position
        """
        return {tool: tower.position for tool, tower in self.towers.items()}
