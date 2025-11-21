# Object-Based Layer Batching Results

## Solution Implemented ✅

The G-code processor now correctly implements **object-based batching** for multi-object prints.

## How It Works

### 1. Object Segment Parser (`object_segment_parser.py`)
- Parses each physical layer
- Detects tool changes WITHIN layers
- Splits each layer into separate object segments
- Result: 256 object segments from 128 physical layers (2 objects per layer)

### 2. Object Batching (`gcode_processor_simple.py`)
- Groups object segments by tool
- Creates batches of consecutive layers for each object
- Alternates between tools in batches
- Maintains proper layer ordering

## Results

### Input G-code Structure (OrcaSlicer for Bambu Lab P1P)
```
Physical Layer 1:
  - Object 55 (Tool 0)
  - [Tool Change T0→T1]
  - Object 108 (Tool 1)

Physical Layer 2:
  - Object 108 (Tool 1) 
  - [Tool Change T1→T0]
  - Object 55 (Tool 0)

...alternating pattern for 128 layers
```

### Output G-code Structure (Object-Batched)
```
Batch 1 (Tool 0): Object 55 for layers 1-10
Batch 2 (Tool 1): Object 108 for layers 1-10
Batch 3 (Tool 0): Object 55 for layers 11-20
Batch 4 (Tool 1): Object 108 for layers 11-20
Batch 5 (Tool 0): Object 55 for layers 21-30
Batch 6 (Tool 1): Object 108 for layers 21-30
...continuing for all 128 layers
```

### Statistics

| Metric | Original | Batched | Improvement |
|--------|----------|---------|-------------|
| **Tool Changes** | 127 | 25 | **80% reduction** |
| **Total Layers** | 128 physical | 128 physical | Same |
| **Object Segments** | 256 | 256 | Same |
| **Batches** | N/A | 26 | Organized |
| **Avg Batch Size** | 1 layer | 9.8 segments | 10x larger |

## Usage

### Basic Usage
```bash
python gcode_processor_simple.py input.gcode output.gcode
```

### With Custom Batch Size
```bash
python gcode_processor_simple.py input.gcode output.gcode --max-batch-layers 20
```

This will batch up to 20 layers per object before switching tools.

## Benefits

1. **Fewer Tool Changes**: 80% reduction means much faster printing
2. **Cleaner Prints**: Less oozing and stringing during tool changes
3. **Better Organization**: Complete layers of each object printed together
4. **Preserved Quality**: All original G-code commands and settings maintained
5. **Header Preserved**: All Bambu Lab configuration and filament settings kept

## Files

- **`gcode_processor_simple.py`**: Main processor with object-based batching
- **`object_segment_parser.py`**: Parser that splits layers by object
- **`gcode_parser.py`**: Base G-code parser
- **`output_object_batched.gcode`**: Example output file

## Technical Details

The processor:
1. Preserves the complete header block (filament settings, machine config)
2. Detects tool changes within layers using T0/T1 commands
3. Captures tool change sequences (heating, flushing, wiping)
4. Splits commands before/after tool changes into separate segments
5. Groups segments by tool and layer number
6. Creates alternating batches with configurable size
7. Writes optimized G-code with proper tool change sequences

## What Changed

**Before**: Print 1 layer of Object A, switch tool, print 1 layer of Object B, switch tool, repeat 128 times

**After**: Print 10 layers of Object A, switch tool, print 10 layers of Object B, switch tool, repeat 13 times

This dramatically reduces print time and improves quality by minimizing tool change overhead!
