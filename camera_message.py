"""https://iotdesignpro.com/projects/real-time-license-plate-recognition-using-raspberry-pi-and-python"""
#!/usr/bin/env python3
import cv2
import imutils
import numpy as np
import pytesseract

camera = cv2.VideoCapture(0)


def capture_license_plate():
    # read USB camera
    frame = camera.read()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  # convert to grayscale
    gray = cv2.bilateralFilter(gray, 11, 17, 17)  # blur to reduce noise
    edged = cv2.Canny(gray, 30, 200)  # perform Edge detection
    # find contours of license plate
    cnts = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)
    cnts = sorted(cnts, key = cv2.contourArea, reverse = True)[:10]
    screenCnt = None
    # draw rectangle around license plate
    for c in cnts:
      peri = cv2.arcLength(c, True)
      approx = cv2.approxPolyDP(c, 0.018 * peri, True)
      if len(approx) == 4:
        screenCnt = approx
        break  # exit for-loop if full rectangle is drawn
    # make sure the contour is properly detected
    if screenCnt is None:
      detected = 0
      print ("No contour detected")
    else:
      detected = 1
    # draw the actual rectangle
    if detected == 1:
      cv2.drawContours(frame, [screenCnt], -1, (0, 255, 0), 3)
    # cut out license plate
    mask = np.zeros(gray.shape,np.uint8)
    new_image = cv2.drawContours(mask,[screenCnt],0,255,-1,)
    new_image = cv2.bitwise_and(frame,frame,mask=mask)
    (x, y) = np.where(mask == 255)
    (topx, topy) = (np.min(x), np.min(y))
    (bottomx, bottomy) = (np.max(x), np.max(y))
    Cropped = gray[topx:bottomx+1, topy:bottomy+1]
    # read license plate
    text = pytesseract.image_to_string(Cropped, config='--psm 6')
    cv2.imshow("Frame", frame)
    cv2.imshow('Cropped',Cropped)
    cv2.waitKey(0)
    return text


while True:
        ret, frame = camera.read()
        cv2.imshow("frame", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("s"):
             gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) #convert to grey scale
             gray = cv2.bilateralFilter(gray, 11, 17, 17) #Blur to reduce noise
             edged = cv2.Canny(gray, 30, 200) #Perform Edge detection
             cnts = cv2.findContours(edged.copy(), cv2.RETR_TREE,              cv2.CHAIN_APPROX_SIMPLE)
             cnts = imutils.grab_contours(cnts)
             cnts = sorted(cnts, key = cv2.contourArea, reverse = True)[:10]
             screenCnt = None
             for c in cnts:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.018 * peri, True)
                if len(approx) == 4:
                  screenCnt = approx
                  break
             if screenCnt is None:
               detected = 0
               print ("No contour detected")
             else:
               detected = 1
             if detected == 1:
               cv2.drawContours(frame, [screenCnt], -1, (0, 255, 0), 3)
             mask = np.zeros(gray.shape,np.uint8)
             new_image = cv2.drawContours(mask,[screenCnt],0,255,-1,)
             new_image = cv2.bitwise_and(frame,frame,mask=mask)
             (x, y) = np.where(mask == 255)
             (topx, topy) = (np.min(x), np.min(y))
             (bottomx, bottomy) = (np.max(x), np.max(y))
             Cropped = gray[topx:bottomx+1, topy:bottomy+1]
             text = pytesseract.image_to_string(Cropped, config='--psm 6')
             print("Detected Number is:",text)
             cv2.imshow("Frame", frame)
             cv2.imshow('Cropped',Cropped)
             cv2.waitKey(0)
             break
             
cv2.destroyAllWindows()