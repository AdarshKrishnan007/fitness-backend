from pymongo import MongoClient
from pymongo import DESCENDING
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os

# Connect to MongoDB Atlas or localhost if not set
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(mongo_uri)

db = client["fitness_app"]
users = db["users"]
progress = db["workout_progress"]

# Register user
from werkzeug.security import generate_password_hash, check_password_hash

def register_user(email, password):
    if users.find_one({"email": email}):
        return {"error": "Email already exists"}

    hashed_pw = generate_password_hash(password)
    user_data = {
        "email": email,
        "password": hashed_pw,
        "user_id": email,  # or generate a unique ID here instead of email
        "total_score": 0,
        "total_xp": 0,
        "workouts_completed": 0,
    }

    users.insert_one(user_data)
    return {"message": "User registered successfully"}


def login_user(email, password):
    user = users.find_one({"email": email})
    if not user:
        return {"error": "User not found"}

    if not check_password_hash(user["password"], password):
        return {"error": "Invalid password"}

    return {
        "message": "Login successful",
        "email": user["email"],
        "user_id": user["user_id"]
    }
    

def get_level_from_xp(xp, max_level=30):
    total_required_xp = 0
    for level in range(1, max_level + 1):
        required_xp = int(100 * (level ** 1.5))
        total_required_xp += required_xp
        if xp < total_required_xp:
            return level - 1 if level > 1 else 1
    return max_level

def calculate_max_xp_for_level(level):
    total = 0
    for l in range(1, level + 1):
        total += int(100 * (l ** 1.5))
    return total

def calculate_max_score_for_level(level):
    # Example: Assuming each level requires 50 * level score.
    total = 0
    for l in range(1, level + 1):
        total += 50 * l
    return total



def normalize_all_users():
    all_users = users.find()
    for user in all_users:
        updates = {}

        # Normalize 'user_id' and 'email'
        user_id = user.get("user_id") or user.get("email")
        updates["user_id"] = user_id
        updates["email"] = user.get("email", user_id)

        # Set default fields
        xp = user.get("total_xp", 0)
        updates["level"] = get_level_from_xp(xp)
        updates["total_score"] = user.get("total_score", 0)
        updates["total_xp"] = user.get("total_xp", 0)
        updates["workouts_completed"] = user.get("workouts_completed", 0)
        updates["total_reps"] = user.get("total_reps", 0)

        # Preserve password if exists
        if "password" in user:
            updates["password"] = user["password"]

        # Optional: preserve workout snapshot
        for field in ["exercise", "completed", "reps", "score", "xp", "timestamp"]:
            if field in user:
                updates[field] = user[field]

        users.update_one({"_id": user["_id"]}, {"$set": updates})


# Workout progress
def save_workout_progress(user_id, exercise, level, score, xp, completed, reps=0,calories=0):
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    workout_data = {
        "date": today_str,
        "user_id": user_id,
        "exercise": exercise,
        "level": level,
        "score": score,
        "xp": xp,
        "reps": int(reps),            # <-- Add reps here
        "completed": completed,
        "timestamp": datetime.utcnow(),
        "calories":calories,
    }
    users.update_one(
        {"user_id": user_id, "exercise": exercise, "level": level},
        {"$set": workout_data},
        upsert=True
    )
    progress.insert_one(workout_data)

    if completed:
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        users.update_one(
            {"user_id": user_id},
            {"$addToSet": {"played_dates": today_str}}  # Add date to user document
        )

def update_user_stats(user_id, score=0, xp=0, completed=False, reps=0, calories=0, **kwargs):
    # Step 1: Fetch current XP
    user = users.find_one({"user_id": user_id})
    current_xp = user.get("total_xp", 0) if user else 0
    new_xp = current_xp + xp
    
    new_level = get_level_from_xp(new_xp)
    new_max_xp = calculate_max_xp_for_level(new_level)
    new_max_score = calculate_max_score_for_level(new_level)

    update_fields = {
        "$inc": {
            "total_score": score,
            "total_xp": xp,
            "total_reps": int(reps),
            "calories": calories,
        },
        "$set": {
            "level": new_level,
            "max_xp": new_max_xp,
            "max_score": new_max_score
        }
    }

    if completed:
        update_fields["$inc"]["workouts_completed"] = 1
        update_fields["$set"]["score.completed"] = True

    for key, value in kwargs.items():
        update_fields["$set"][key] = value

    users.update_one(
        {"user_id": user_id},
        update_fields,
        upsert=True
    )





def get_user_stats(user_id):
    
    user = users.find_one(
        {"user_id": user_id},
        {
            "_id": 0,
            "user_id": 1,
            "total_score": 1,
            "total_xp": 1,
            "max_xp": 1,
            "max_score": 1,
            "workouts_completed": 1,
            "total_reps": 1,
            "goals": 1,
            "level": 1,
            "height": 1,
            "weight": 1,
            "age": 1,
            "gender": 1,
            "name":1,
            "calories":1,
            "played_dates": 1,
            "unlocked_level": 1,
        }
    )

    if not user:
        return {
            "user_id": user_id,
            "total_score": 0,
            "total_xp": 0,
            "workouts_completed": 0,
            "total_reps": 0,
            "max_xp_for_level": calculate_max_xp_for_level(2),
            "max_score_for_level": calculate_max_score_for_level(2),
            "goals": 0,
            "level": 0,
            "height": None,
            "weight": None,
            "age": None,
            "gender": None,
            "name":None,
            "calories":0,
            
        }
    total_xp = user.get("total_xp", 0)
    user["level"] = get_level_from_xp(total_xp)

    # Calculate max XP/Score for the next level (for progress bar)
    next_level = user["level"] + 1
    user["max_xp_for_level"] = calculate_max_xp_for_level(next_level)
    user["max_score_for_level"] = calculate_max_score_for_level(next_level)
    activities = progress.find({"user_id": user_id})
    activities_by_date = {}

    for doc in activities:
        timestamp = doc.get("timestamp")
        if not timestamp:
          continue

        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp)
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            continue

        date_key = dt.strftime("%Y-%m-%d")
        activities_by_date.setdefault(date_key, []).append({
            "exercise": doc.get("exercise"),
            "level": doc.get("level"),
            "reps": doc.get("reps"),
            "xp": doc.get("xp"),
            "calories": doc.get("calories"),
        })

    user["activities_by_date"] = activities_by_date
    return user

def get_leaderboard(limit=10, sort_by="total_xp"):
    db1 = db
    pipeline = [
        {
            "$match": {
                "email": {"$exists": True},  # filters out workout logs
                "name": {"$exists": True}
            }
        },
        {
            "$project": {
                "_id": 0,
                "user_id": 1,
                "name": 1,
                "total_xp": 1,
                "total_score": 1,
                "level": 1
            }
        },
        {
            "$sort": {sort_by: -1}
        },
        {
            "$limit": limit
        }
    ]
    users = list(db1.users.aggregate(pipeline))
    return users

