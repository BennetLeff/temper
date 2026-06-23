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
cdef int state_to_index(int row, int col, int layer, int width, int height, int num_layers)
cdef void index_to_state(int index, int* row, int* col, int* layer, int width, int height, int num_layers)

# GridView for direct memory access
cdef struct GridView:
    int* data
    int width
    int height
    int num_layers
    unsigned long long* bitmap
    int bitmap_row_stride

cdef int grid_get(GridView* grid, int row, int col, int layer)
cdef bint grid_is_available(GridView* grid, int row, int col, int layer, int net_id)
cdef bint grid_is_available_bitmap(GridView* grid, int row, int col, int layer, int net_id)

# Heuristic function
cdef float heuristic(int row1, int col1, int layer1, int row2, int col2, int layer2, float cell_size, float via_cost)
