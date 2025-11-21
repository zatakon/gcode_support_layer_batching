#!/usr/bin/env python3
"""Example test script to demonstrate the layer batching processor.

This script creates a simple test G-code file and processes it to show
the layer batching optimization in action.
"""

from gcode_processor import GCodeProcessor
from pathlib import Path


def generate_test_gcode() -> str:
    """Generate a simple test G-code file with alternating materials.
    
    Returns:
        Path to the generated test file
    """
    test_file = 'test_input.gcode'
    
    with open(test_file, 'w') as f:
        # Header
        f.write("; Test G-code for layer batching\n")
        f.write("G21 ; millimeters\n")
        f.write("G90 ; absolute positioning\n")
        f.write("M82 ; absolute extrusion\n")
        f.write("\n")
        
        # Create 20 layers alternating between T0 (primary) and T1 (support)
        layer_height = 0.2
        
        for layer_num in range(1, 21):
            z = layer_num * layer_height
            
            # Alternate tools: odd layers = T0, even layers = T1
            tool = layer_num % 2
            
            f.write(f"; Layer {layer_num}\n")
            f.write(f"T{tool}\n")
            f.write(f"G1 Z{z:.3f} F300\n")
            
            # Draw a simple square (20x20mm)
            if tool == 0:  # Primary material (larger square)
                coords = [
                    (10, 10), (30, 10), (30, 30), (10, 30), (10, 10)
                ]
            else:  # Support material (smaller square inside)
                coords = [
                    (15, 15), (25, 15), (25, 25), (15, 25), (15, 15)
                ]
            
            # Move to start
            f.write(f"G1 X{coords[0][0]:.1f} Y{coords[0][1]:.1f} F3000\n")
            
            # Draw perimeter with extrusion
            for i in range(1, len(coords)):
                x, y = coords[i]
                f.write(f"G1 X{x:.1f} Y{y:.1f} E{i * 0.5:.4f}\n")
            
            f.write("\n")
        
        # Footer
        f.write("; End of test file\n")
        f.write("M104 S0\n")
        f.write("M140 S0\n")
    
    return test_file


def main():
    """Run the test example."""
    print("=" * 60)
    print("Layer Batching Test Example")
    print("=" * 60)
    print()
    
    # Generate test file
    print("Step 1: Generating test G-code file...")
    input_file = generate_test_gcode()
    print(f"Created: {input_file}")
    print()
    
    # Process with layer batching
    print("Step 2: Processing with layer batching...")
    output_file = 'test_output.gcode'
    
    processor = GCodeProcessor(
        nozzle_diameter=0.4,
        collision_margin=1.0,
        max_batch_layers=10,
        zhop_height=0.5,
        enable_prime_towers=True
    )
    
    try:
        processor.process_file(input_file, output_file)
        print()
        print("=" * 60)
        print("SUCCESS!")
        print("=" * 60)
        print()
        print(f"Input file:  {input_file}")
        print(f"Output file: {output_file}")
        print()
        print("Compare the two files to see the optimization:")
        print(f"  - Original: 20 layers with ~20 tool changes")
        print(f"  - Optimized: Batched layers with fewer tool changes")
        print()
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
