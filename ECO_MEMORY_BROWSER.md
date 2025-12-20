# ECO Memory Browser Architecture

Based on the ECO memory server and the viewer.js frontend, here is the architecture for the ECO memory browser:

## Server

The ECO memory server runs at https://eco.bennetleff.workers.dev and provides:

- REST API for searching and storing memories
- WebSocket interface for real-time updates
- Vector database backend using Cloudflare Vectorize
- D1 SQL database for structured storage

## Frontend

The viewer.js file in temper-placer/src/temper_placer/visualization/static/viewer.js contains the live visualization viewer that connects to the WebSocket server.

### Components

- **WebSocket Client**: Manages connection to the ECO server
- **State Management**: Tracks current connection status, training state, and current placement data
- **UI Updates**: Updates various UI elements based on incoming data
- **Board Visualization**: Renders the PCB layout using Plotly
- **Loss Curves**: Shows training loss over time
- **Loss Breakdown**: Displays contribution of different loss components
- **Controls**: Provides buttons to pause/resume, step iterations, and export state 

### Connection Flow

1. Page loads and initializes
2. WebSocket connects to server via ws://localhost:8765 (or wss:// for HTTPS)
3. On connection, requests current state
4. Receives state updates, training events, and errors
5. UI updates in real-time

## HTML Structure

The index.html file provides the UI structure with:

- Header with connection status
- Main board visualization panel
- Side panels for loss curves and breakdown
- Status panel with metrics and controls
- Overlay for connection messages

## Potential Namespace Sources

Looking at the code and ECO memories, potential namespace options include:

- "reflective" - From memory.primarySector in search results
- "procedural" - From memory.primarySector in search results 
- "semantic" - From memory.primarySector in search results
- "temporality" - Common vector memory sector
- "episodic" - Common vector memory sector
- "planner" - Common agent role
- "coder" - Common agent role
- "architect" - Common agent role
- "temper-placer" - Project specific
- "firmware" - Project specific
- "design" - Common memory category
- "research" - Common memory category
- "meeting-notes" - Common memory category
- "project-tracking" - Common memory category