import sys
import ctypes
from ctypes import POINTER, byref, c_void_p, c_ulong, c_int, c_wchar_p, c_uint

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QMenu,
                             QAction, QSlider, QWidget, QVBoxLayout, QLabel, QHBoxLayout,
                             QDesktopWidget, QRadioButton, QButtonGroup, QMessageBox, QAbstractButton)
from PyQt5.QtGui import QIcon, QPixmap, QPalette, QColor, QPainter # Added QPalette, QColor, QPainter
from PyQt5.QtCore import Qt, QPoint, QEvent, QSize, QTimer, QByteArray # Added QByteArray
from PyQt5.QtSvg import QSvgRenderer # Added QSvgRenderer for SVG icons

# ============================================================
# Constants and Definitions (Copied directly from your provided project, with one critical change)
# ============================================================

# COM and context constants
COINIT_APARTMENTTHREADED = 0x2 # CRITICAL FIX: Changed to STA for GUI applications
CLSCTX_ALL = 23

# Device selection enumerations (from mmdeviceapi.h)
EDataFlow_eRender = 0    # Render devices (e.g., speakers)
ERole_eConsole          = 0    # Console role
ERole_eMultimedia       = 1    # Multimedia role
ERole_eCommunications   = 2    # Communications role

# Device state mask
DEVICE_STATE_ACTIVE = 0x00000001

# Load COM functions from ole32.dll
ole32 = ctypes.windll.ole32

# -------------------------------
# GUID and Helper Structures
# -------------------------------
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8)
    ]

def create_guid(guid_str):
    """
    Converts a GUID string (e.g., "BCDE0395-E52F-467C-8E3D-C4579291692E")
    into a GUID structure.
    """
    parts = guid_str.split('-')
    data1 = int(parts[0], 16)
    data2 = int(parts[1], 16)
    data3 = int(parts[2], 16)
    data4_bytes = bytes.fromhex(parts[3] + parts[4])
    data4 = (ctypes.c_ubyte * 8).from_buffer_copy(data4_bytes)
    return GUID(data1, data2, data3, data4)

# GUIDs from header files:
CLSID_MMDeviceEnumerator = create_guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator   = create_guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_IAudioEndpointVolume  = create_guid("5CDF2C82-841E-4546-9722-0CF74078229A")

# For switching default device, we use the undocumented IPolicyConfig interface.
# These GUIDs are commonly used in the community.
CLSID_CPolicyConfigClient = create_guid("870AF99C-171D-4F9E-AF0D-E63DF40C2BC9")
IID_IPolicyConfig         = create_guid("F8679F50-850A-41CF-9C72-430F290290C8") 

# -------------------------------
# PROPERTYKEY and PROPVARIANT (for friendly names)
# -------------------------------
class PROPERTYKEY(ctypes.Structure):
    _fields_ = [
        ("fmtid", GUID),
        ("pid", ctypes.c_ulong)
    ]

# For our purposes we only handle VT_LPWSTR (VT value 31)
VT_LPWSTR = 31

class PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("wReserved2", ctypes.c_ushort),
        ("wReserved3", ctypes.c_ushort),
        ("pwszVal", ctypes.c_wchar_p)
    ]

# Define PKEY_Device_FriendlyName:
# {A45C254E-DF1C-4EFD-8020-67D146A850E0}, 14
PKEY_Device_FriendlyName = PROPERTYKEY(create_guid("A45C254E-DF1C-4EFD-8020-67D146A850E0"), 14)

# ============================================================
# COM Initialization and IMMDeviceEnumerator Creation
# ============================================================
def init_com():
    """Initialize the COM library."""
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr < 0:
        raise ctypes.WinError(hr)

def create_device_enumerator():
    """Creates an instance of MMDeviceEnumerator and returns its pointer."""
    pEnumerator = c_void_p()
    hr = ole32.CoCreateInstance(
        byref(CLSID_MMDeviceEnumerator),
        None,
        CLSCTX_ALL,
        byref(IID_IMMDeviceEnumerator),
        byref(pEnumerator)
    )
    if hr < 0:
        raise ctypes.WinError(hr)
    return pEnumerator

# ============================================================
# IMMDeviceEnumerator Interface (VTable and Interface)
# ============================================================
class IMMDeviceEnumeratorVTable(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ("Release",        ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ("EnumAudioEndpoints", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_int, c_ulong, POINTER(c_void_p))),
        ("GetDefaultAudioEndpoint", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_int, c_int, POINTER(c_void_p))),
        ("GetDevice",      ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, POINTER(c_void_p))),
        ("RegisterEndpointNotificationCallback", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_void_p)),
        ("UnregisterEndpointNotificationCallback", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_void_p))
    ]

class IMMDeviceEnumerator_Interface(ctypes.Structure):
    _fields_ = [("lpVtbl", POINTER(IMMDeviceEnumeratorVTable))]

def get_default_endpoint(enumerator_ptr):
    """
    Uses the IMMDeviceEnumerator interface to obtain the default audio endpoint.
    """
    enumerator_iface = ctypes.cast(enumerator_ptr, POINTER(IMMDeviceEnumerator_Interface))
    default_endpoint = c_void_p()
    hr = enumerator_iface.contents.lpVtbl.contents.GetDefaultAudioEndpoint(
        enumerator_iface,
        EDataFlow_eRender,
        ERole_eConsole,
        byref(default_endpoint)
    )
    if hr < 0:
        raise ctypes.WinError(hr)
    return default_endpoint

# ============================================================
# IMMDevice Interface (for Activate, OpenPropertyStore, and GetId)
# ============================================================
class IMMDeviceVTable(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ("Release",        ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ("Activate",       ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), c_ulong, c_void_p, POINTER(c_void_p))),
        ("OpenPropertyStore", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_ulong, POINTER(c_void_p))),
        ("GetId",          ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_wchar_p))),
        ("GetState",       ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_ulong)))
    ]

class IMMDevice_Interface(ctypes.Structure):
    _fields_ = [("lpVtbl", POINTER(IMMDeviceVTable))]

def activate_audio_endpoint_volume(endpoint_ptr):
    """
    Activates the IAudioEndpointVolume interface for the given endpoint.
    """
    endpoint_iface = ctypes.cast(endpoint_ptr, POINTER(IMMDevice_Interface))
    audio_endpoint_volume = c_void_p()
    hr = endpoint_iface.contents.lpVtbl.contents.Activate(
        endpoint_iface,
        byref(IID_IAudioEndpointVolume),
        CLSCTX_ALL,
        None,
        byref(audio_endpoint_volume)
    )
    if hr < 0:
        raise ctypes.WinError(hr)
    return audio_endpoint_volume

def get_device_id(device_ptr):
    """
    Uses the IMMDevice interface to get the device's ID (a string).
    """
    device_iface = ctypes.cast(device_ptr, POINTER(IMMDevice_Interface))
    pDeviceId = c_wchar_p()
    hr = device_iface.contents.lpVtbl.contents.GetId(device_iface, byref(pDeviceId))
    if hr < 0:
        raise ctypes.WinError(hr)
    return pDeviceId.value

# ============================================================
# IAudioEndpointVolume Interface (VTable and Interface)
# ============================================================
class IAudioEndpointVolumeVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))),
        ("AddRef",         ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ("Release",        ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
        ("RegisterControlChangeNotify", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_void_p)),
        ("UnregisterControlChangeNotify", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_void_p)),
        ("GetChannelCount", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_uint))),
        ("SetMasterVolumeLevel", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, ctypes.c_float, c_void_p)),
        ("SetMasterVolumeLevelScalar", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, ctypes.c_float, c_void_p)),
        ("GetMasterVolumeLevel", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(ctypes.c_float))),
        ("GetMasterVolumeLevelScalar", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(ctypes.c_float))),
        ("SetChannelVolumeLevel", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint, ctypes.c_float, c_void_p)),
        ("SetChannelVolumeLevelScalar", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint, ctypes.c_float, c_void_p)),
        ("GetChannelVolumeLevel", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint, POINTER(ctypes.c_float))),
        ("GetChannelVolumeLevelScalar", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint, POINTER(ctypes.c_float))),
        ("SetMute", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_int, c_void_p)),
        ("GetMute", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_int))),
        ("GetVolumeStepInfo", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_uint), POINTER(c_uint))),
        ("VolumeStepUp", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_void_p)),
        ("VolumeStepDown", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_void_p)),
        ("QueryHardwareSupport", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_ulong))),
        ("GetVolumeRange", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(ctypes.c_float), POINTER(ctypes.c_float), POINTER(ctypes.c_float)))
    ]

class IAudioEndpointVolume_Interface(ctypes.Structure):
    _fields_ = [("lpVtbl", POINTER(IAudioEndpointVolumeVtbl))]

# ============================================================
# Volume Control Helper Functions (using ctypes interfaces)
# ============================================================
def volume_step_up(audio_volume_ptr):
    volume_iface = ctypes.cast(audio_volume_ptr, POINTER(IAudioEndpointVolume_Interface))
    hr = volume_iface.contents.lpVtbl.contents.VolumeStepUp(volume_iface, None)
    if hr < 0:
        raise ctypes.WinError(hr)

def volume_step_down(audio_volume_ptr):
    volume_iface = ctypes.cast(audio_volume_ptr, POINTER(IAudioEndpointVolume_Interface))
    hr = volume_iface.contents.lpVtbl.contents.VolumeStepDown(volume_iface, None)
    if hr < 0:
        raise ctypes.WinError(hr)

def set_mute(audio_volume_ptr, mute: bool):
    volume_iface = ctypes.cast(audio_volume_ptr, POINTER(IAudioEndpointVolume_Interface))
    hr = volume_iface.contents.lpVtbl.contents.SetMute(volume_iface, int(mute), None)
    if hr < 0:
        raise ctypes.WinError(hr)

def get_mute(audio_volume_ptr) -> bool:
    mute_val = c_int()
    volume_iface = ctypes.cast(audio_volume_ptr, POINTER(IAudioEndpointVolume_Interface))
    hr = volume_iface.contents.lpVtbl.contents.GetMute(volume_iface, byref(mute_val))
    if hr < 0:
        raise ctypes.WinError(hr)
    return bool(mute_val.value)

def get_master_volume_scalar(audio_volume_ptr) -> float:
    volume_iface = ctypes.cast(audio_volume_ptr, POINTER(IAudioEndpointVolume_Interface))
    level = ctypes.c_float()
    hr = volume_iface.contents.lpVtbl.contents.GetMasterVolumeLevelScalar(volume_iface, byref(level))
    if hr < 0:
        raise ctypes.WinError(hr)
    return level.value

def set_master_volume_scalar(audio_volume_ptr, value: float):
    volume_iface = ctypes.cast(audio_volume_ptr, POINTER(IAudioEndpointVolume_Interface))
    # FIX: Re-added 'volume_iface' as the first argument
    hr = volume_iface.contents.lpVtbl.contents.SetMasterVolumeLevelScalar(volume_iface, ctypes.c_float(value), None)
    if hr < 0:
        raise ctypes.WinError(hr)

# ============================================================
# IPropertyStore Interface (for Friendly Names)
# ============================================================
class IPropertyStoreVtbl(ctypes.Structure):
    _fields_ = [
             ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))),
             ("AddRef", ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
             ("Release", ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
             ("GetCount", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_uint))),
             ("GetAt", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint, POINTER(PROPERTYKEY))),
             ("GetValue", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(PROPERTYKEY), POINTER(PROPVARIANT)))
    ]

class IPropertyStore_Interface(ctypes.Structure):
    _fields_ = [("lpVtbl", POINTER(IPropertyStoreVtbl))]

# Helper to release COM objects (defined once at the top)
def release_com_object(ptr):
    if ptr and ptr.value: # Check if pointer is not null
        try:
            # All COM interfaces inherit from IUnknown, and Release is at VTable index 2
            class IUnknownVTable(ctypes.Structure):
                _fields_ = [
                    ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))),
                    ("AddRef", ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
                    ("Release", ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p))
                ]
            class IUnknown_Interface(ctypes.Structure):
                _fields_ = [("lpVtbl", POINTER(IUnknownVTable))]

            iface = ctypes.cast(ptr, POINTER(IUnknown_Interface))
            iface.contents.lpVtbl.contents.Release(iface)
        except Exception as e:
            pass


def get_device_friendly_name(device_ptr):
    """
    Opens the property store for the device and retrieves the friendly name.
    """
    pPropertyStore = None # Initialize to None
    try:
        device_iface = ctypes.cast(device_ptr, POINTER(IMMDevice_Interface))
        pPropertyStore = c_void_p()
        hr = device_iface.contents.lpVtbl.contents.OpenPropertyStore(device_iface, 0, byref(pPropertyStore))
        if hr < 0:
            raise ctypes.WinError(hr)
        prop_store = ctypes.cast(pPropertyStore, POINTER(IPropertyStore_Interface))
        propvar = PROPVARIANT()
        hr = prop_store.contents.lpVtbl.contents.GetValue(prop_store, byref(PKEY_Device_FriendlyName), byref(propvar)) 
        if hr < 0:
            raise ctypes.WinError(hr)
        return propvar.pwszVal
    finally:
        release_com_object(pPropertyStore) # Release the property store pointer

# ============================================================
# IMMDeviceCollection Interface (for Enumerating Devices)
# ============================================================
class IMMDeviceCollectionVTable(ctypes.Structure):
    _fields_ = [
             ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))),
             ("AddRef", ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
             ("Release", ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
             ("GetCount", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(c_uint))),
             ("Item", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_uint, POINTER(c_void_p)))
    ]

class IMMDeviceCollection_Interface(ctypes.Structure):
    _fields_ = [("lpVtbl", POINTER(IMMDeviceCollectionVTable))]


def enumerate_audio_endpoints(enumerator_ptr):
    """
    Enumerates all active render devices and returns a list of dictionaries:
    {'ptr': device pointer, 'name': friendly name, 'id': device ID string}
    """
    pCollection = None # Initialize to None
    devices = []
    try:
        enumerator_iface = ctypes.cast(enumerator_ptr, POINTER(IMMDeviceEnumerator_Interface))
        pCollection = c_void_p()
        hr = enumerator_iface.contents.lpVtbl.contents.EnumAudioEndpoints(
            enumerator_iface,
            EDataFlow_eRender,
            DEVICE_STATE_ACTIVE,
            byref(pCollection)
        )
        if hr < 0:
            raise ctypes.WinError(hr)
        collection_iface = ctypes.cast(pCollection, POINTER(IMMDeviceCollection_Interface))
        count = c_uint()
        hr = collection_iface.contents.lpVtbl.contents.GetCount(collection_iface, byref(count))
        if hr < 0:
            raise ctypes.WinError(hr)
        
        for i in range(count.value):
            pDevice = None # Initialize to None for each iteration
            try:
                pDevice = c_void_p()
                hr = collection_iface.contents.lpVtbl.contents.Item(collection_iface, i, byref(pDevice))
                if hr < 0:
                    continue # Skip this device if Item fails
                
                name = get_device_friendly_name(pDevice) # This function now releases pPropertyStore
                device_id = get_device_id(pDevice)
                devices.append({"ptr": pDevice, "name": name, "id": device_id})
                # IMPORTANT: pDevice is added to the list. It should NOT be released here,
                # as it's passed to the UI and will be used later.
                # Its Release will be handled by the UI elements if they store it,
                # or when the app exits.
            except Exception as e:
                release_com_object(pDevice) # Release if an error occurred before adding to list
                pass # Skip devices that cause errors
    finally:
        release_com_object(pCollection) # Release the collection pointer
    return devices

# ============================================================
# IPolicyConfig Interface (Undocumented, for switching default device)
# ============================================================
class IPolicyConfigVtbl(ctypes.Structure):
    _fields_ = [
             ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, POINTER(GUID), POINTER(c_void_p))),
             ("AddRef", ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
             ("Release", ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)),
             ("GetMixFormat", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, POINTER(c_void_p))),
             ("GetDeviceFormat", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, c_int, POINTER(c_void_p))),
             ("SetDeviceFormat", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, c_void_p, c_void_p)),
             ("GetProcessingPeriod", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, c_int, POINTER(ctypes.c_longlong), POINTER(ctypes.c_longlong))),
             ("SetProcessingPeriod", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, POINTER(ctypes.c_longlong))),
             ("GetShareMode", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, POINTER(c_void_p))),
             ("SetShareMode", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, c_void_p)),
             ("GetPropertyValue", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))),
             ("SetPropertyValue", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))),
             ("SetDefaultEndpoint", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, c_int)),
             ("SetEndpointVisibility", ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, c_wchar_p, c_int))
    ]

class IPolicyConfig_Interface(ctypes.Structure):
    _fields_ = [("lpVtbl", POINTER(IPolicyConfigVtbl))]

# Define new GUIDs for IPolicyConfigVista based on the provided header snippet:
CLSID_CPolicyConfigVistaClient = create_guid("294935CE-F637-4E7C-A41B-AB255460B862")
IID_IPolicyConfigVista = create_guid("568B9108-44BF-40B4-9006-86AFE5B5A620")

def switch_default_device(device_ptr):
    """
    Switches the default audio endpoint to the given device.
    Uses the reverse-engineered IPolicyConfigVista interface.
    Attempts to set the default endpoint for eConsole, eMultimedia, and eCommunications roles.
    If a call fails with "The tag is invalid" (error -2147023163), it logs a warning and continues.
    """
    pPolicyConfig = None
    try:
        device_id = get_device_id(device_ptr)

        pPolicyConfig = c_void_p()
        hr = ole32.CoCreateInstance(
                 byref(CLSID_CPolicyConfigVistaClient),
                 None,
                 CLSCTX_ALL,
                 byref(IID_IPolicyConfigVista),
                 byref(pPolicyConfig)
        )
        if hr < 0:
                 raise ctypes.WinError(hr)

        policy_config = ctypes.cast(pPolicyConfig, POINTER(IPolicyConfig_Interface))
        
        roles = [ERole_eConsole, ERole_eMultimedia, ERole_eCommunications]
        success_count = 0
        for role in roles:
            hr = policy_config.contents.lpVtbl.contents.SetDefaultEndpoint(policy_config, device_id, role)
            if hr < 0:
                if hr == -2147023163:
                    pass
                else:
                    print(f"SetDefaultEndpoint for role {role} failed with unexpected error: {ctypes.WinError(hr)}")
            else:
                success_count += 1
        
        if success_count > 0:
            print(f"Default device switched to: '{device_id}' for {success_count} roles.")
            return True
        else:
            print(f"Failed to set default device '{device_id}' for any role.")
            return False
    except Exception as e:
        print(f"Error in switch_default_device: {e}")
        raise
    finally:
        release_com_object(pPolicyConfig)


# ============================================================
# PyQt5 Application (Modified to use ctypes functions)
# ============================================================

# SVG for a headphone icon
SVG_HEADPHONE_ICON = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
  <path d="M12 1a9 9 0 0 0-9 9v7c0 1.65 1.35 3 3 3h3v-8H5v-2a7 7 0 0 1 7-7zm0 18a7 7 0 0 1 7-7v-2h-4v8h3c1.65 0 3-1.35 3-3v-7a9 9 0 0 0-9-9z"/>
</svg>
"""

def create_svg_icon(svg_string, size=QSize(20, 20)):
    """Creates a QIcon from an SVG string."""
    renderer = QSvgRenderer(QByteArray(svg_string.encode('utf-8')))
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class VolumeControlApp(QWidget):
    def __init__(self, enumerator_ptr, initial_default_endpoint_ptr):
        super().__init__()

        self.enumerator_ptr = enumerator_ptr
        self.current_audio_volume_ptr = None

        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setWindowTitle("Volume Control")

        main_layout = QVBoxLayout()

        # Volume Slider and Label
        slider_layout = QHBoxLayout()
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        
        self.volume_slider.setValue(0) 
        self.volume_slider.valueChanged.connect(self.set_system_volume_qt)
        
        self.volume_label = QLabel(f"0%")
        self.volume_label.setAlignment(Qt.AlignCenter)
        slider_layout.addWidget(self.volume_slider)
        slider_layout.addWidget(self.volume_label)
        main_layout.addLayout(slider_layout)
        
        main_layout.addSpacing(10)
        main_layout.addWidget(QLabel("Output Devices:"))

        self.device_layout = QVBoxLayout()
        self.device_button_group = QButtonGroup(self)
        self.device_button_group.setExclusive(True)
        self.device_button_group.buttonToggled.connect(self.change_audio_output_qt)

        main_layout.addLayout(self.device_layout)

        self.setLayout(main_layout)
        self.installEventFilter(self)

        # Timer to periodically refresh volume and device list
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_ui)
        self.refresh_timer.start(1000)

        # Initial population on startup
        self.populate_devices_qt()
        self.update_volume_from_system_qt()

    def refresh_ui(self):
        """Refreshes both device list and volume status."""
        self.populate_devices_qt()
        self.update_volume_from_system_qt()

    def set_system_volume_qt(self, value: int):
        """Sets system master volume from slider value (0-100)."""
        if self.current_audio_volume_ptr:
            set_master_volume_scalar(self.current_audio_volume_ptr, value / 100.0)
            self.volume_label.setText(f"{value}%")

    def update_volume_from_system_qt(self):
        """Updates the slider and label from actual system volume of the current default device."""
        default_endpoint_ptr = None
        try:
            default_endpoint_ptr = get_default_endpoint(self.enumerator_ptr)
            if default_endpoint_ptr:
                if self.current_audio_volume_ptr:
                    release_com_object(self.current_audio_volume_ptr)
                    self.current_audio_volume_ptr = None
                
                self.current_audio_volume_ptr = activate_audio_endpoint_volume(default_endpoint_ptr)
                
                current_volume_scalar = get_master_volume_scalar(self.current_audio_volume_ptr)
                current_volume_percent = int(current_volume_scalar * 100)
                
                self.volume_slider.blockSignals(True) 
                self.volume_slider.setValue(current_volume_percent)
                self.volume_slider.blockSignals(False)
                
                self.volume_label.setText(f"{current_volume_percent}%")
            else:
                self.volume_slider.setValue(0)
                self.volume_label.setText("N/A")
                self.current_audio_volume_ptr = None
        except Exception as e:
            print(f"Error updating volume from system: {e}")
            self.volume_slider.setValue(0)
            self.volume_label.setText("Error")
            self.current_audio_volume_ptr = None
        finally:
            release_com_object(default_endpoint_ptr)


    def populate_devices_qt(self):
        # Clear existing device buttons and labels
        for i in reversed(range(self.device_layout.count())):
            widget_to_remove = self.device_layout.itemAt(i).widget()
            if widget_to_remove:
                if isinstance(widget_to_remove, QAbstractButton):
                    self.device_button_group.removeButton(widget_to_remove)
                self.device_layout.removeWidget(widget_to_remove)
                widget_to_remove.deleteLater()

        devices = enumerate_audio_endpoints(self.enumerator_ptr)
        current_default_id = None
        default_endpoint_ptr_temp = None 
        try:
            default_endpoint_ptr_temp = get_default_endpoint(self.enumerator_ptr)
            if default_endpoint_ptr_temp:
                current_default_id = get_device_id(default_endpoint_ptr_temp)
        except Exception as e:
            print(f"Could not get current default device ID: {e}")
        finally:
            release_com_object(default_endpoint_ptr_temp)

        self.device_button_group.blockSignals(True)

        if devices:
            headphone_icon = create_svg_icon(SVG_HEADPHONE_ICON)
            for device in devices:
                radio_button = QRadioButton(device["name"])
                radio_button.setProperty("device_id", device["id"])
                radio_button.setProperty("device_ptr", device["ptr"])
                radio_button.setIcon(headphone_icon)
                self.device_layout.addWidget(radio_button)
                self.device_button_group.addButton(radio_button)

                if device["id"] == current_default_id:
                    radio_button.setChecked(True)
        else:
            no_devices_label = QLabel("No active playback devices found.")
            self.device_layout.addWidget(no_devices_label)

        self.device_button_group.blockSignals(False)


    def change_audio_output_qt(self, button: QRadioButton, checked: bool):
        if checked:
            device_ptr_to_switch = button.property("device_ptr")
            if device_ptr_to_switch:
                try:
                    if switch_default_device(device_ptr_to_switch):
                        if self.current_audio_volume_ptr:
                            release_com_object(self.current_audio_volume_ptr)
                            self.current_audio_volume_ptr = None
                        
                        new_default_endpoint_ptr = None
                        try:
                            new_default_endpoint_ptr = get_default_endpoint(self.enumerator_ptr)
                            if new_default_endpoint_ptr:
                                self.current_audio_volume_ptr = activate_audio_endpoint_volume(new_default_endpoint_ptr)
                                self.update_volume_from_system_qt()
                        finally:
                            release_com_object(new_default_endpoint_ptr)
                        
                        self.populate_devices_qt() 
                    else:
                        QMessageBox.warning(self, "Switch Failed", 
                                             "Failed to set default audio device for any role.\n"
                                             "This might require administrator privileges or the device may not support the default roles.")
                        self.populate_devices_qt()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to switch default device: {e}\n"
                                         "You might need to run the application as Administrator.")
                    self.populate_devices_qt()


    def eventFilter(self, obj, event):
        if obj == self and event.type() == QEvent.WindowDeactivate:
            self.hide()
        return super().eventFilter(obj, event)

class SystemTrayApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)

        # Set Dark Mode Palette
        self.setStyle("Fusion") # Recommended for dark themes
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(128, 128, 128)) # Grey out disabled text
        dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(128, 128, 128)) # Grey out disabled buttons
        self.setPalette(dark_palette)


        # Initialize COM and get device enumerator once
        try:
            init_com()
            self.device_enumerator_ptr = create_device_enumerator()
            self.initial_default_endpoint_ptr = get_default_endpoint(self.device_enumerator_ptr)
        except Exception as e:
            QMessageBox.critical(None, "Initialization Error", f"Failed to initialize audio system: {e}\n"
                                 "Please ensure your audio drivers are working and try running as Administrator.")
            sys.exit(1)

        # Try to load icon from file, fall back if not found
        try:
            # Load icon using the base_path for py2exe/PyInstaller compatibility
            # This path logic is only relevant if using PyInstaller's --add-data
            # For py2exe, if outputcontrol_icon.ico is in data_files, it will be in the root of the dist folder.
            self.tray_icon = QSystemTrayIcon(QIcon("outputcontrol_icon.ico")) 
        except Exception:
            self.tray_icon = QSystemTrayIcon(QIcon()) # Fallback to no icon or default
            QMessageBox.warning(None, "Icon Missing", "outputcontrol_icon.ico not found. Please place it in the same directory or bundle correctly.")
            
        self.tray_icon.setToolTip("OutputControl")

        menu = QMenu()
        quit_action = QAction("Quit", menu)
        transparent_pixmap = QPixmap(1, 1)
        transparent_pixmap.fill(Qt.transparent)
        transparent_icon = QIcon(transparent_pixmap)
        quit_action.setIcon(transparent_icon)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)

        self.tray_icon.activated.connect(self.tray_icon_activated)

        self.volume_control_window = VolumeControlApp(self.device_enumerator_ptr, self.initial_default_endpoint_ptr)

        self.tray_icon.show()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_volume_control_at_cursor()

    def show_volume_control_at_cursor(self):
        self.volume_control_window.refresh_ui()

        cursor_pos = self.tray_icon.geometry().center()

        desktop = QApplication.desktop()
        screen_number = desktop.screenNumber(cursor_pos)
        screen_geometry = desktop.screenGeometry(screen_number)

        window_width = 280 
        
        num_devices = len(enumerate_audio_endpoints(self.device_enumerator_ptr)) 
        
        window_height = 110 + (num_devices * 25) + 20 
        if window_height < 180:
            window_height = 180

        # Position the window near the tray icon (bottom-right corner of the screen)
        x = screen_geometry.x() + screen_geometry.width() - window_width - 100
        y = screen_geometry.y() + screen_geometry.height() - window_height - 65

        self.volume_control_window.setGeometry(x, y, window_width, window_height)

        self.volume_control_window.show()
        self.volume_control_window.activateWindow()
        self.volume_control_window.raise_()

if __name__ == "__main__":
    app = SystemTrayApp(sys.argv)
    sys.exit(app.exec_())