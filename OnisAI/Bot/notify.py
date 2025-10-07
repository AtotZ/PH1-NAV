# Local iOS push notifications (via objc_util)

import time
import webbrowser
from objc_util import ObjCClass

# Objective-C classes
UNUserNotificationCenter = ObjCClass("UNUserNotificationCenter")
UNMutableNotificationContent = ObjCClass("UNMutableNotificationContent")
UNNotificationRequest = ObjCClass("UNNotificationRequest")
UNTimeIntervalNotificationTrigger = ObjCClass("UNTimeIntervalNotificationTrigger")
UNNotificationSound = ObjCClass("UNNotificationSound")


def open_uber():
    """Open Uber Driver app via URL scheme."""
    webbrowser.open("uberdriver://")


def push_local(title: str, body: str, delay: float = 0.5):
    """
    Schedule a local notification after `delay` seconds.
    Uses a unique identifier per request to avoid overwriting pending alerts.
    """
    content = UNMutableNotificationContent.alloc().init()
    content.setTitle_(title)
    content.setBody_(body)
    content.setSound_(UNNotificationSound.defaultSound())

    trigger = UNTimeIntervalNotificationTrigger.triggerWithTimeInterval_repeats_(delay, False)

    # Unique identifier: milliseconds since epoch
    req_id = f"TripPushNotif-{int(time.time() * 1000)}"
    request = UNNotificationRequest.requestWithIdentifier_content_trigger_(req_id, content, trigger)

    center = UNUserNotificationCenter.currentNotificationCenter()
    center.addNotificationRequest_withCompletionHandler_(request, None)
