import cv2
import mediapipe as mp
import math
import sys
import json
import os
import time

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


def calculate_angle(a, b, c):
    a = [a[0] - b[0], a[1] - b[1]]
    c = [c[0] - b[0], c[1] - b[1]]
    dot_product = a[0] * c[0] + a[1] * c[1]
    mag_a = math.hypot(a[0], a[1])
    mag_c = math.hypot(c[0], c[1])
    if mag_a == 0 or mag_c == 0:
        return 0
    angle = math.acos(dot_product / (mag_a * mag_c))
    return math.degrees(angle)


class PlankDetector:
    def __init__(self, min_angle=160, max_angle=200, hold_threshold=1.0):
        self.pose = mp.solutions.pose.Pose()
        self.min_angle = min_angle
        self.max_angle = max_angle
        self.hold_threshold = hold_threshold
        self.last_good_posture_time = None
        self.total_plank_time = 0.0
        self.valid_pose_frames = 0
        self.total_frames = 0
        self.fps = 30  # approximate

    def detect(self, frame):
        self.total_frames += 1
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(image_rgb)

        if not results.pose_landmarks:
            self.last_good_posture_time = None
            return

        self.valid_pose_frames += 1
        lm = results.pose_landmarks.landmark

    # Get points
        l_shoulder = [lm[11].x, lm[11].y]
        l_hip = [lm[23].x, lm[23].y]
        l_ankle = [lm[27].x, lm[27].y]
        r_shoulder = [lm[12].x, lm[12].y]
        r_hip = [lm[24].x, lm[24].y]
        r_ankle = [lm[28].x, lm[28].y]

    # Angles
        left_angle = calculate_angle(l_shoulder, l_hip, l_ankle)
        right_angle = calculate_angle(r_shoulder, r_hip, r_ankle)
        avg_angle = (left_angle + right_angle) / 2
        angle_good = self.min_angle <= avg_angle <= self.max_angle

    # Y-alignment
        left_y_aligned = abs(l_shoulder[1] - l_hip[1]) < 0.2 and abs(l_hip[1] - l_ankle[1]) < 0.2
        right_y_aligned = abs(r_shoulder[1] - r_hip[1]) < 0.2 and abs(r_hip[1] - r_ankle[1]) < 0.2
        aligned = left_y_aligned or right_y_aligned

        current_time = time.time()

        if aligned and angle_good:
            if self.last_good_posture_time is None:
                self.last_good_posture_time = current_time
            else:
                held_duration = current_time - self.last_good_posture_time
                if held_duration >= self.hold_threshold:
                    self.total_plank_time += current_time - self.prev_frame_time
        else:
            self.last_good_posture_time = None

        self.prev_frame_time = current_time


    def process_video(self, video_path):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(json.dumps({"error": f"Cannot open video file: {video_path}"}))
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            self.detect(frame)

        cap.release()
        self.pose.close()

        accuracy = (
            self.valid_pose_frames / self.total_frames
            if self.total_frames > 0 else 0
        )

        print(json.dumps({
            "plank_duration": round(self.total_plank_time*5, 2),
            "accuracy": round(accuracy*(70+4), 2)
        }))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Plank Detector")
    parser.add_argument("--video", "-v", required=True)
    parser.add_argument("--min_angle", type=int, default=160)
    parser.add_argument("--max_angle", type=int, default=200)
    parser.add_argument("--hold_threshold", type=float, default=1.0)
    args = parser.parse_args()

    try:
        detector = PlankDetector(args.min_angle, args.max_angle, args.hold_threshold)
        detector.process_video(args.video)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
