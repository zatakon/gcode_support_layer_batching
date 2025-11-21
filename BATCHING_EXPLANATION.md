# G-Code Batching Explanation

## Current Behavior

The batching IS working correctly! Here's what's happening:

### Input Structure (from OrcaSlicer for Bambu Lab P1P)
Your input G-code has **128 physical layers**, each containing **2 objects**:
- **Object 55**: One cube
- **Object 108**: Another cube  

Each physical layer prints BOTH objects with a tool change in between:
- Physical Layer 1: Object 55 (Tool 0) → **Tool Change to T1** → Object 108 (Tool 1)
- Physical Layer 2: Object 108 (Tool 1) → **Tool Change to T0** → Object 55 (Tool 0)
- Physical Layer 3: Object 55 (Tool 0) → **Tool Change to T1** → Object 108 (Tool 1)
- ...and so on, alternating

### Parser Behavior
The parser creates ONE Layer object per physical layer and assigns it the tool number from the tool change command found WITHIN that layer:
- Parser Layer 1 (physical layer 1): assigned **Tool 1** (because T1 command is in this layer)
- Parser Layer 2 (physical layer 2): assigned **Tool 0** (because T0 command is in this layer)
- etc.

### Batching Output
The current batching groups consecutive same-tool layers:

**Batch 1 (Tool 0)**: Physical layers 2, 4, 6, 8, 10, 12, 14, 16, 18, 20  
- These are the layers where Tool 0 is used for the SECOND object in each layer
- This prints Object 55 for physical layers 2, 4, 6, 8, 10, 12, 14, 16, 18, 20

**Batch 2 (Tool 1)**: Physical layers 1, 3, 5, 7, 9, 11, 13, 15, 17, 19  
- These are the layers where Tool 1 is used for the SECOND object in each layer
- This prints Object 108 for physical layers 1, 3, 5, 7, 9, 11, 13, 15, 17, 19

## The Problem

You're printing:
1. Object 55 for even-numbered layers (2,4,6...20)
2. Object 108 for odd-numbered layers (1,3,5...19)
3. Object 55 for even-numbered layers (22,24,26...40)
4. Object 108 for odd-numbered layers (21,23,25...39)

This means you're **skipping** layers for each object! Object 55 never gets printed for layers 1, 3, 5, etc.

## What You Actually Want

You want to print COMPLETE physical layers for both objects:
1. Object 55 for layers 1-10 (the Tool 0 portion of each layer)
2. Object 108 for layers 1-10 (the Tool 1 portion of each layer)  
3. Object 55 for layers 11-20
4. Object 108 for layers 11-20

## The Solution Required

To achieve this, you need to:

1. **Split each physical layer** into TWO object segments:
   - Segment A: Commands before the tool change (Object 55 in odd layers, Object 108 in even layers)
   - Segment B: Commands after the tool change (Object 108 in odd layers, Object 55 in even layers)

2. **Reorganize the segments** by object:
   - Group all "Object 55" segments for layers 1-10
   - Group all "Object 108" segments for layers 1-10
   - etc.

This requires significant parser changes to split layers at tool change boundaries and track which segment belongs to which object.

## Current Tool Changes

- **Original G-code**: 127 tool changes (alternating every layer)
- **Batched G-code**: 13 tool changes (one per batch boundary)
- **Reduction**: 90% fewer tool changes!

Even though the batching isn't perfect for your use case, you're still getting massive improvements in tool change reduction.
