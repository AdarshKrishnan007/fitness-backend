import cv2
import mediapipe as mp
import sys
import json
import os

# Suppress TensorFlow and MediaPipe logs
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

class JumpDetector:
    def __init__(self, upward_threshold=10.0, downward_threshold=8.0):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose()
        self.jump_count = 0
        self.prev_y = None
        self.upward_threshold = upward_threshold
        self.downward_threshold = downward_threshold
        self.in_air = False
        self.total_frames = 0
        self.valid_pose_frames = 0

    def detect(self, frame):
        self.total_frames += 1
        # Convert BGR to RGB as mediapipe expects RGB images
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(frame_rgb)

        if results.pose_landmarks:
            self.valid_pose_frames += 1
            # Get left and right hip landmarks
            left_hip = results.pose_landmarks.landmark[self.mp_pose.PoseLandmark.LEFT_HIP]
            right_hip = results.pose_landmarks.landmark[self.mp_pose.PoseLandmark.RIGHT_HIP]
            
            # Calculate average y position of hips in pixels
            frame_height = frame.shape[0]
            current_hip_y = ((left_hip.y + right_hip.y) / 2) * frame_height

            print(f"[Debug] Hip Y position: {current_hip_y:.2f}", file=sys.stderr)

            if self.prev_y is not None:
                diff = current_hip_y - self.prev_y  # Negative if moving up
                print(f"[Debug] Vertical movement diff: {diff:.2f}, In air: {self.in_air}, Jump count: {self.jump_count}", file=sys.stderr)


                # Detect lift-off (moving up fast enough and not already in air)
                if diff < -self.upward_threshold and not self.in_air:
                    self.in_air = True
                    print(f"[Jump] Detected lift-off. diff: {diff:.2f}", file=sys.stderr)

                # Detect landing (moving down fast enough and currently in air)
                elif diff > self.downward_threshold and self.in_air:
                    self.in_air = False
                    self.jump_count += 1
                    print(f"[Jump] Landing detected. Count: {self.jump_count}", file=sys.stderr)

            self.prev_y = current_hip_y
        else:
            print("[Warning] No pose landmarks detected in this frame.", file=sys.stderr)


    def process_video(self, video_path):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(json.dumps({"error": f"Cannot open video file: {video_path}"}), file=sys.stdout)

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

        print(json.dumps({"jump_count": self.jump_count, "accuracy": round(accuracy*70, 2)}))



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Jump Detector - Video Only")
    parser.add_argument("--video", "-v", required=True, help="Path to video file")
    parser.add_argument("--upward", "-u", type=float, default=10.0, help="Upward jump detection threshold in pixels")
    parser.add_argument("--downward", "-d", type=float, default=8.0, help="Downward landing detection threshold in pixels")

    args = parser.parse_args()

    try:
        detector = JumpDetector(upward_threshold=args.upward, downward_threshold=args.downward)
        detector.process_video(args.video)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
