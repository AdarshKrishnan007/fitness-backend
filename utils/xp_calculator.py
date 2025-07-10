def calculate_xp_and_score(reps, user_weight_kg, exercise_duration_sec, exercise_type, accuracy=0):
    # MET values for different exercises
    MET_VALUES = {
        'jump': 8.0,
        'squat': 5.0,
        'pushup': 8.0,
        'plank': 4.0,
    }

    # Get MET value for this exercise; default to 5 if not found
    met = MET_VALUES.get(exercise_type, 5.0)  # default MET value
    met = float(met) 
    
    user_weight_kg = float(user_weight_kg)
    exercise_duration_sec = float(exercise_duration_sec)
    # Convert duration from seconds to hours
    duration_hr = exercise_duration_sec / 3600

    # Calculate calories burned using MET formula
    calories = met * user_weight_kg * duration_hr

    # Basic scoring and XP calculations (you can adjust as needed)
    
    xp = reps * 10
    score = reps * 5
    completed = reps > 0  # You can define your own completion logic

    return {
        "xp": xp,
        "score": score,
        "completed": completed,
        "reps": reps,
        "calories": round(calories, 2),
        "accuracy": accuracy # round calories to 2 decimal places
    }
