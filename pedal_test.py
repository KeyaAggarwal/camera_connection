import hid

# List all HID devices
print("Listing all HID devices:")
for device in hid.enumerate():
    print(f"Vendor ID: {device['vendor_id']:#06x}, Product ID: {device['product_id']:#06x}, Path: {device['path']}")

# Try to open your specific device
try:
    print("\nAttempting to open your foot pedal...")
    pedal = hid.device()
    pedal.open(0x04b4, 0x5555)  # Use your actual vendor/product IDs
    print("Success! Device opened.")
    pedal.close()
except Exception as e:
    print(f"Error opening device: {e}")