import cv2

# 1. Choose the correct monitor index
# 0 is usually your main monitor, 1 is usually the projector
PROJECTOR_MONITOR_INDEX = 1 

# 2. Create a named window with normal flags first
window_name = "Projector_Output"
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

# 3. Move the window to the projector's screen area 
# (Assuming your main monitor is 1920x1080; adjust if screens overlap differently)
cv2.moveWindow(window_name, 1920 * PROJECTOR_MONITOR_INDEX, 0)

# 4. Force the window into a borderless, full-screen view
cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

# Initialize your camera, video, or frame generation logic
cap = cv2.VideoCapture(3)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Process your frame here if needed
    
    # 5. Display the frame on the projector window
    cv2.imshow(window_name, frame)

    # Break loop on 'q' key press
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
