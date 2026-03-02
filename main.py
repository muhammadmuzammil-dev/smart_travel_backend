# backend/main.py

# Import FastAPI to create the app, and the routes for user, itinerary, and chatbot
from routes import user, itinerary, chatbot, fare, feedback, budget
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Initialize the FastAPI app
app = FastAPI()  # Core application that will handle all requests

# Configure CORS to allow requests from mobile app and ngrok
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Register routes for different functionalities
# - User management (login, preferences)
# - Itinerary generation
# - Chatbot interaction
app.include_router(user.router, prefix="/user", tags=["user"])
app.include_router(itinerary.router, prefix="/itinerary", tags=["itinerary"])
app.include_router(chatbot.router, prefix="/chatbot", tags=["chatbot"])
app.include_router(fare.router,     prefix="/fare",     tags=["fare"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
app.include_router(budget.router,   prefix="/budget",   tags=["budget"])

# Simple root route for testing if the server is running
@app.get("/")
async def root():
    return {"message": "Welcome to the Smart Itinerary Planner backend!"}  
