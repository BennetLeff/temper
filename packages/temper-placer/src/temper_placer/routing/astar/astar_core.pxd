# cython: language_level=3

"""Cython header file for A* core data structures.

This file will define the C structs and function signatures for the high-performance
A* implementation. Currently a placeholder - will be implemented in Phase 2.
"""

# MinHeap data structures (Phase 2 - temper-6te4.2)
cdef struct HeapNode:
    float priority
    int state_index

cdef struct MinHeap:
    HeapNode* nodes
    int size
    int capacity

# Function declarations (to be implemented)
cdef void heap_init(MinHeap* heap, int capacity)
cdef void heap_push(MinHeap* heap, float priority, int state_index)
cdef int heap_pop(MinHeap* heap, float* priority)
cdef void heap_free(MinHeap* heap)

# State indexing functions
cdef inline int state_to_index(int row, int col, int layer, int width, int height, int num_layers)
cdef inline void index_to_state(int index, int* row, int* col, int* layer, int width, int height, int num_layers)

# GridView for direct memory access
cdef struct GridView:
    int* data
    int width
    int height
    int num_layers

cdef inline int grid_get(GridView* grid, int row, int col, int layer)
cdef inline bint grid_is_available(GridView* grid, int row, int col, int layer, int net_id)

# Heuristic function
cdef inline float heuristic(int row1, int col1, int layer1, int row2, int col2, int layer2, float cell_size, float via_cost)
