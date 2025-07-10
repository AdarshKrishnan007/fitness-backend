from flask import Flask, request, jsonify
from flask_cors import CORS
from models.user_data import update_user_stats, get_user_stats, save_workout_progress,get_leaderboard
from utils.xp_calculator import calculate_xp_and_score
from models.user_data import login_user, register_user

import subprocess
import os
import traceback
import json

from models.user_data import normalize_all_users
from werkzeug.exceptions import RequestEntityTooLarge 

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
CORS(app, supports_credentials=True, origins=["http://localhost:3000"])


@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(e):
    return jsonify({'success': False, 'message': 'File too large'}), 413

# In-memory user progress store (replace with DB in production)
user_progress = {}

@app.route('/')
def index():
    return "Server is running!"


@app.route("/user/setup", methods=["POST"])
def setup_user_profile():
    data = request.get_json()
    print("Incoming data:", data) 
    user_id = data.get("user_id")  # This should come from login/registration flow

    profile = {
        "name": data.get("name"),
        "age": data.get("age"),
        "gender": data.get("gender"),
        "height": data.get("height"),
        "weight": data.get("weight"),
        "goal": data.get("goal")
    }

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    try:
        # Store this data in your database
        update_user_stats(user_id=user_id, **profile)  # You can also create a new DB method like `save_user_profile`
        return jsonify({"success": True, "message": "Profile saved successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# New /start route to only save frontend detection data (already processed data)
@app.route('/start', methods=['POST'])
def save_frontend_data():
    data = request.get_json()
    user_id = data.get('user_id')
    # Other detection data fields expected from frontend
    exercise = data.get('exercise')
    level = data.get('level')
    score = data.get('score', 0)
    xp = data.get('xp', 0)
    reps = int(data.get('reps', 0))
    completed = data.get('completed', False)

    if not user_id:
        return jsonify({'success': False, 'message': 'Missing user_id'}), 400

    # Save workout progress (frontend detection data)
    save_workout_progress(user_id, exercise, level, score, xp, completed, reps)

    # Update cumulative stats based on frontend data
    update_user_stats(user_id, score=score, xp=xp, completed=completed, reps=reps)

    # Update in-memory progress for quick access
    progress = user_progress.get(user_id, {"total_xp": 0, "completed_exercises": 0})
    progress["total_xp"] += xp
    if completed:
        progress["completed_exercises"] += 1
    user_progress[user_id] = progress

    return jsonify({'success': True, 'message': 'Frontend detection data saved successfully'})

# Renamed original /start route to /upload
@app.route('/upload', methods=['POST'])
def upload_and_process():
    ex_type = request.form.get('exercise')
    user_id = request.form.get('user_id') or "1"  # fallback for now
    video = request.files.get('video')
    

    if not ex_type or not user_id or not video:
        return jsonify({'success': False, 'message': 'Missing workout type, user_id, or video'}), 400

    video_path = f"uploads/{user_id}_{ex_type}.mp4"
    os.makedirs("uploads", exist_ok=True)
    video.save(video_path)

    # Manually set video duration (fallback)
    exercise_duration_sec = 10  # set manually if moviepy not used

    script_path = f"detectors/{ex_type}_detector.py"
    if not os.path.exists(script_path):
        return jsonify({'success': False, 'message': 'Invalid workout type'}), 400

    try:
        result = subprocess.run(
            ['python', script_path, '--video', video_path],
            capture_output=True,
            text=True
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode != 0:
            return jsonify({'success': False, 'error': error}), 500

        # Parse detector output JSON
        try:
            parsed_output = json.loads(output)
            if ex_type == "jump":
                 reps = int(parsed_output.get("jump_count", 0))
            elif ex_type == "squat":
                reps = int(parsed_output.get("squat_count", 0))
            elif ex_type == "pushup":
                reps = int(parsed_output.get("pushup_count", 0))
            elif ex_type == "plank":
                reps = int(parsed_output.get("plank_duration", 0))  # or another metric
            else:
                reps = 0

            accuracy = parsed_output.get("accuracy", 0)# or generalize key for other exercises
        except json.JSONDecodeError:
            return jsonify({'success': False, 'error': 'Invalid output format from detector script'}), 500

        # Fetch user weight for calorie calculation
        user_stats = get_user_stats(user_id)
        user_weight_kg = user_stats.get("weight") or 70  # fallback weight if none

        # Calculate score, xp, calories
        score_data = calculate_xp_and_score(
            reps,
            exercise_duration_sec=exercise_duration_sec,
            user_weight_kg=user_weight_kg,
            exercise_type=ex_type,
            accuracy=accuracy,
        )

        update_user_stats(
            user_id=user_id,
            score=score_data.get("score", 0),
            xp=score_data.get("xp", 0),
            completed=score_data.get("completed", False),
            reps=score_data.get("reps", 0),
            calories=score_data.get("calories", 0),
            accuracy=score_data.get("accuracy", 0)
        )

        # Update in-memory progress
        progress = user_progress.get(user_id, {"total_xp": 0, "completed_exercises": 0})
        progress["total_xp"] += score_data.get("xp", 0)
        if score_data.get("completed"):
            progress["completed_exercises"] += 1
        user_progress[user_id] = progress

        return jsonify({
            'success': True,
            'reps': reps,
            'score': score_data
        })

    except Exception as e:
        tb = traceback.format_exc()
        print("Error in /upload:", tb)
        return jsonify({'success': False, 'error': str(e), 'traceback': tb}), 500

    
@app.route("/workout/unlock-level", methods=["POST"])
def unlock_next_level():
    data = request.get_json()
    user_id = data.get("user_id")
    level = data.get("currentLevel")  # Expected format: "Level1", "Level2", etc.

    if not user_id or not level:
        return jsonify({"success": False, "message": "Missing user_id or level"}), 400

    try:
        # Extract number from "LevelX"
        if isinstance(level, str) and level.lower().startswith("level"):
            current_level_num = int(level[5:])  # Level5 -> 5
            next_level = f"Level{current_level_num + 1}"
        else:
            return jsonify({"success": False, "message": "Invalid level format"}), 400

        # Update MongoDB user's document to persist the unlocked level
        update_user_stats(user_id, unlocked_level=next_level)

        return jsonify({
            "success": True,
            "message": f"Unlocked next level: {next_level}",
            "unlockedLevel": next_level
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/user/stats', methods=['GET'])
def get_stats():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'Missing user_id'}), 400

    # Remove int() conversion if user_id is an email
    stats = get_user_stats(user_id=user_id)
    return jsonify(stats)




@app.route("/workout/progress", methods=["POST"])
def get_today_progress():
    data = request.get_json()  # Properly parse JSON body
    user_id = data.get("user_id") if data else None

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    progress = user_progress.get(user_id, {"total_xp": 0, "completed_exercises": 0})

    return jsonify({
        "user_id": user_id,
        "total_xp": progress.get("total_xp", 0),
        "completed_exercises": progress.get("completed_exercises", 0)
    })


@app.route("/workout/log", methods=["POST"])
def log_workout():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid or missing JSON"}), 400

        user_id = data.get("user_id")
        exercise = data.get("exercise")
        level = data.get("level")
        score = data.get("score", 0)
        xp = data.get("xp", 0)
        reps = data.get("reps", 0)
        completed = data.get("completed", False)
        calories = data.get("calories", 0)

        if not all([user_id, exercise, level]):
            return jsonify({"error": "Missing required fields"}), 400

        print(f"[Workout Log] user: {user_id}, exercise: {exercise}, level: {level}")

        # Save workout progress
        save_workout_progress(user_id, exercise, level, score, xp, completed, reps, calories)

        # Update cumulative stats
        update_user_stats(user_id, score=score, xp=xp, completed=completed, reps=reps, calories=float(calories))

        return jsonify({"message": "Workout logged successfully"}), 200

    except Exception as e:
        print("[Workout Log ERROR]:", str(e))
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    result = register_user(email, password)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    result = login_user(email, password)

    if "error" in result:
        return jsonify(result), 401
    return jsonify(result)

@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    sort_by = request.args.get("sort_by", "total_xp")  # now matches field name
    try:
        leaderboard_data = get_leaderboard(sort_by=sort_by)
        return jsonify({"success": True, "leaderboard": leaderboard_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/admin/normalize', methods=['POST'])
def normalize_user_data():
    try:
        normalize_all_users()
        return jsonify({"success": True, "message": "User data normalized"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    

if __name__ == '__main__':
    app.run(port=5001, debug=True)
