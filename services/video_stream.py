import cv2
import threading
import time
import queue
from core.logger import logger

class VideoStream:
    def __init__(self, source, queue_size=128):
        self.source = source
        self.stream = cv2.VideoCapture(source)
        self.queue = queue.Queue(maxsize=queue_size)
        self.stopped = False
        self.thread = None
        self.fps = self.stream.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.stream.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if not self.stream.isOpened():
            logger.error(f"Failed to open video source: {source}")
            raise ValueError(f"Unable to open {source}")
            
    def start(self):
        """Start the thread to read frames from the video stream."""
        self.stopped = False
        self.thread = threading.Thread(target=self.update, args=(), daemon=True)
        self.thread.start()
        return self

    def update(self):
        """Keep looping infinitely until the thread is stopped."""
        while True:
            if self.stopped:
                return

            if not self.queue.full():
                grabbed, frame = self.stream.read()
                
                if not grabbed:
                    logger.info("End of video stream reached.")
                    self.stop()
                    return
                
                self.queue.put(frame)
            else:
                time.sleep(0.01) # Wait if queue is full

    def read(self):
        """Return the next frame in the queue."""
        if self.queue.empty():
            return None
        return self.queue.get()

    def more(self):
        """Return True if there are still frames in the queue."""
        return self.queue.qsize() > 0 or not self.stopped

    def stop(self):
        """Indicate that the thread should be stopped."""
        self.stopped = True
        if self.thread and self.thread.is_alive():
            self.thread.join()
        if self.stream.isOpened():
            self.stream.release()
