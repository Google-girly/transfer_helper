# Transfer Helper

Transfer Helper is a full-stack web application designed to help students evaluate how completed courses transfer between California colleges and universities. The application allows users to select a source institution, a destination institution, enter completed courses, and view articulation results using structured academic transfer data.

This project focuses on improving transparency and accessibility in transfer planning by providing a simplified, interactive interface on top of complex articulation datasets.

## Features

- Interactive frontend for selecting source and destination institutions
- Autocomplete school search powered by institution metadata
- Batch course lookup to evaluate transfer equivalencies
- Displays course matches, GE areas, and approval status
- Client-side state persistence for entered courses
- Clean, responsive UI designed for student usability

## Architecture Overview

The project is split into a frontend and backend with a clear separation of concerns.

### Frontend

- Built with HTML, CSS, and vanilla JavaScript
- Uses Bootstrap for layout and styling
- Handles user input, validation, and UI rendering
- Persists entered course data using localStorage
- Communicates with the backend via REST API calls

### Backend

- Implemented in Python
- Exposes REST endpoints for:
  - Retrieving institution lists
  - Processing batch transfer lookups
- Processes and normalizes large articulation datasets
- Returns structured JSON responses for frontend consumption

## Data Processing

Transfer Helper relies on preprocessed academic articulation data derived from public transfer resources.

Backend scripts are used to:

- Fetch institution metadata and codes
- Normalize articulation agreements into simplified lookup formats
- Reduce large datasets into efficient, queryable structures
- Support batch course queries for performance and usability

## API Endpoints (High Level)

- **GET /schools** - Returns a list of institutions with display names and internal codes
- **POST /lookup_batch** - Accepts a source school, destination school, and list of courses, and returns structured articulation results

## Running the Project Locally

### Prerequisites

- Python 3.x
- Node.js (if applicable)
- A virtual environment tool (optional but recommended)

### Backend

1. Navigate to the backend directory
2. Create and activate a virtual environment
3. Install dependencies from `requirements.txt`
4. Run the backend server

### Frontend

1. Navigate to the frontend directory
2. Install dependencies if needed
3. Start the frontend server
4. Open the application in your browser

The frontend communicates with the backend over localhost during development.

## Project Goals

- Simplify transfer planning for students
- Make articulation data more accessible and understandable
- Provide a foundation that can be extended into larger academic planning tools
- Explore full-stack development with real-world data constraints

## Future Improvements

- Deploy backend and frontend to a cloud environment
- Add authentication for saved transfer plans
- Improve course matching
- Add a pdf parser

## Disclaimer

This project is intended for educational and planning purposes only. Official transfer decisions should always be confirmed with academic advisors and institutional policies.
