import sys
import ctypes
import os
import configparser
from ctypes import POINTER, byref, c_void_p, c_ulong, c_int, c_wchar_p, c_uint

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QMenu,
                             QAction, QSlider, QWidget, QVBoxLayout, QLabel, QHBoxLayout,
                             QDesktopWidget, QRadioButton, QButtonGroup, QMessageBox, QAbstractButton,
                             QPushButton, QSizePolicy, QSpacerItem, QFrame, QActionGroup, QStyle)
from PyQt5.QtGui import QIcon, QPixmap, QPalette, QColor
from PyQt5.QtCore import Qt, QPoint, QEvent, QSize, QTimer, pyqtSignal

# Added for cursor position
from PyQt5.QtGui import QCursor

# --- Base path for bundled resources (for PyInstaller/py2exe) ---
if hasattr(sys, '_MEIPASS'):
    base_path = sys._MEIPASS
else:
    base_path = os.path.abspath(".")

# --- Configuration File Management ---
CONFIG_FILE = os.path.join(base_path, 'config.ini')

def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    
    settings = {
        'toggle': True, # Default: widget enabled
        'monitor': 1,    # Default: monitor 1
        'icon_x': 0,     # Default: icon X position
        'icon_y': 0,      # Default: icon Y position
        'icon_size': 48  # Default: icon size (48x48)
    }

    if 'WidgetDisplay' in config:
        if 'toggle' in config['WidgetDisplay']:
            settings['toggle'] = config['WidgetDisplay'].getboolean('toggle')
        if 'monitor' in config['WidgetDisplay']:
            try:
                settings['monitor'] = config['WidgetDisplay'].getint('monitor')
            except ValueError:
                pass 
        if 'icon_x' in config['WidgetDisplay']:
            try:
                settings['icon_x'] = config['WidgetDisplay'].getint('icon_x')
            except ValueError:
                pass
        if 'icon_y' in config['WidgetDisplay']:
            try:
                settings['icon_y'] = config['WidgetDisplay'].getint('icon_y')
            except ValueError:
                pass
        if 'icon_size' in config['WidgetDisplay']:
            try:
                settings['icon_size'] = config['WidgetDisplay'].getint('icon_size')
            except ValueError:
                pass
    return settings

def save_config(toggle_state, monitor_index, icon_x, icon_y, icon_size):
    config = configparser.ConfigParser()
    config['WidgetDisplay'] = {
        'toggle': str(toggle_state),
        'monitor': str(monitor_index),
        'icon_x': str(icon_x),
        'icon_y': str(icon_y),
        'icon_size': str(icon_size)
    }
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

# ============================================================
# Constants and Definitions
# ============================================================

# COM and context constants
COINIT_APARTMENTTHREADED = 0x2
CLSCTX_ALL = 23

# Device selection enumerations (from mmdeviceapi.h)
EDataFlow_eRender = 0
EDataFlow_eCapture = 1 # Added for input devices
ERole_eConsole          = 0
ERole_eMultimedia       = 1
ERole_eCommunications   = 2

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

def get_default_endpoint(enumerator_ptr, data_flow: int, role: int):
    """
    Uses the IMMDeviceEnumerator interface to obtain the default audio endpoint.
    data_flow: EDataFlow_eRender (output) or EDataFlow_eCapture (input)
    role: ERole_eConsole, ERole_eMultimedia, ERole_eCommunications
    """
    enumerator_iface = ctypes.cast(enumerator_ptr, POINTER(IMMDeviceEnumerator_Interface))
    default_endpoint = c_void_p()
    hr = enumerator_iface.contents.lpVtbl.contents.GetDefaultAudioEndpoint(
        enumerator_iface,
        data_flow,
        role,
        byref(default_endpoint)
    )
    if hr < 0:
        # print(f"GetDefaultAudioEndpoint failed for data_flow={data_flow}, role={role}: {ctypes.WinError(hr)}")
        return None # Return None if no default endpoint found or error
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
    if ptr and ptr.value:
        try:
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
    pPropertyStore = None
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
        release_com_object(pPropertyStore)

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


def enumerate_audio_endpoints(enumerator_ptr, data_flow: int):
    """
    Enumerates all active audio endpoints for a given data flow (render/capture)
    and returns a list of dictionaries:
    {'ptr': device pointer, 'name': friendly name, 'id': device ID string}
    """
    pCollection = None
    devices = []
    try:
        enumerator_iface = ctypes.cast(enumerator_ptr, POINTER(IMMDeviceEnumerator_Interface))
        pCollection = c_void_p()
        hr = enumerator_iface.contents.lpVtbl.contents.EnumAudioEndpoints(
            enumerator_iface,
            data_flow,
            DEVICE_STATE_ACTIVE,
            byref(pCollection)
        )
        if hr < 0:
            # print(f"EnumAudioEndpoints failed for data_flow={data_flow}: {ctypes.WinError(hr)}")
            return [] # Return empty list if no devices found or error
        
        collection_iface = ctypes.cast(pCollection, POINTER(IMMDeviceCollection_Interface))
        count = c_uint()
        hr = collection_iface.contents.lpVtbl.contents.GetCount(collection_iface, byref(count))
        if hr < 0:
            # print(f"GetCount failed for data_flow={data_flow}: {ctypes.WinError(hr)}")
            return []
        
        for i in range(count.value):
            pDevice = None
            try:
                pDevice = c_void_p()
                hr = collection_iface.contents.lpVtbl.contents.Item(collection_iface, i, byref(pDevice))
                if hr < 0:
                    continue
                
                name = get_device_friendly_name(pDevice)
                device_id = get_device_id(pDevice)
                devices.append({"ptr": pDevice, "name": name, "id": device_id})
            except Exception as e:
                # print(f"Error processing device {i} for data_flow={data_flow}: {e}")
                release_com_object(pDevice)
                pass
    finally:
        release_com_object(pCollection)
    
    devices.reverse() # Often preferred for display order
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

def switch_default_device(device_ptr, data_flow: int):
    """
    Switches the default audio endpoint to the given device for specific roles.
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
        
        # Roles to set based on data_flow
        roles_to_set = []
        if data_flow == EDataFlow_eRender:
            roles_to_set = [ERole_eConsole, ERole_eMultimedia, ERole_eCommunications]
        elif data_flow == EDataFlow_eCapture:
            roles_to_set = [ERole_eConsole, ERole_eMultimedia, ERole_eCommunications] # Apply to all roles for consistency

        success_count = 0
        for role in roles_to_set:
            hr = policy_config.contents.lpVtbl.contents.SetDefaultEndpoint(policy_config, device_id, role)
            if hr < 0:
                if hr == -2147023163:
                    # print(f"SetDefaultEndpoint for role {role} failed with 'The tag is invalid' (expected for some roles/devices).")
                    pass
                else:
                    print(f"SetDefaultEndpoint for data_flow={data_flow}, role {role} failed with unexpected error: {ctypes.WinError(hr)}")
            else:
                success_count += 1
        
        if success_count > 0:
            print(f"Default device switched to: '{device_id}' for {success_count} roles (DataFlow: {data_flow}).")
            return True
        else:
            print(f"Failed to set default device '{device_id}' for any role (DataFlow: {data_flow}).")
            return False
    except Exception as e:
        print(f"Error in switch_default_device: {e}")
        raise
    finally:
        release_com_object(pPolicyConfig)


# ============================================================
# PyQt5 Application (Modified to use ctypes functions)
# ============================================================

def get_icon(icon_type, size=QSize(20, 20), widget_style=None):
    """
    Creates a QIcon based on type using QStyle.StandardPixmap.
    """
    if not widget_style:
        # Fallback to application style if no widget_style is provided
        widget_style = QApplication.instance().style()

    if icon_type == "mute":
        return widget_style.standardIcon(QStyle.SP_MediaVolumeMuted)
    elif icon_type == "unmute":
        return widget_style.standardIcon(QStyle.SP_MediaVolume)
    elif icon_type == "headphone":
        # Using SP_MediaVolume as a general audio output icon
        return widget_style.standardIcon(QStyle.SP_MediaVolume)
    elif icon_type == "microphone":
        # Using SP_MediaPlay as a general audio input icon (or to differentiate)
        return widget_style.standardIcon(QStyle.SP_MediaPlay)
    else:
        return QIcon() # Return empty icon for unknown type


class FloatingVolumeWidget(QWidget):
    def __init__(self, enumerator_ptr):
        super().__init__()

        self.enumerator_ptr = enumerator_ptr
        self.current_output_audio_volume_ptr = None
        self.current_input_audio_volume_ptr = None

        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setWindowTitle("Volume Control")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Output Devices Section ---
        output_group_box = QFrame(self)
        output_group_box.setFrameShape(QFrame.StyledPanel)
        output_group_box.setFrameShadow(QFrame.Raised)
        output_group_box_layout = QVBoxLayout(output_group_box)
        output_group_box_layout.setContentsMargins(5, 5, 5, 5)
        output_group_box_layout.setSpacing(5)

        output_group_box_layout.addWidget(QLabel("<b>Output Devices:</b>"))

        # Output Volume Slider and Label
        output_slider_layout = QHBoxLayout()
        self.output_volume_slider = QSlider(Qt.Horizontal)
        self.output_volume_slider.setRange(0, 100)
        self.output_volume_slider.setValue(0) 
        self.output_volume_slider.valueChanged.connect(self.set_system_output_volume_qt)
        self.output_volume_label = QLabel(f"0%")
        self.output_volume_label.setAlignment(Qt.AlignCenter)
        output_slider_layout.addWidget(self.output_volume_slider)
        output_slider_layout.addWidget(self.output_volume_label)
        output_group_box_layout.addLayout(output_slider_layout)
        
        # Output Mute Button
        self.output_mute_button = QPushButton("Mute Output")
        self.output_mute_button.setIcon(get_icon("unmute", widget_style=self.style()))
        self.output_mute_button.setCheckable(True)
        self.output_mute_button.setChecked(False) # Assume not muted initially
        self.output_mute_button.toggled.connect(self.toggle_output_mute_qt)
        output_group_box_layout.addWidget(self.output_mute_button)


        self.output_device_layout = QVBoxLayout()
        self.output_device_button_group = QButtonGroup(self)
        self.output_device_button_group.setExclusive(True)
        self.output_device_button_group.buttonToggled.connect(self.change_audio_output_qt)
        output_group_box_layout.addLayout(self.output_device_layout)
        output_group_box_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)) # Spacer

        main_layout.addWidget(output_group_box)

        # --- Input Devices Section ---
        input_group_box = QFrame(self)
        input_group_box.setFrameShape(QFrame.StyledPanel)
        input_group_box.setFrameShadow(QFrame.Raised)
        input_group_box_layout = QVBoxLayout(input_group_box)
        input_group_box_layout.setContentsMargins(5, 5, 5, 5)
        input_group_box_layout.setSpacing(5)

        input_group_box_layout.addWidget(QLabel("<b>Input Devices:</b>"))

        # Input Volume Slider and Label
        input_slider_layout = QHBoxLayout()
        self.input_volume_slider = QSlider(Qt.Horizontal)
        self.input_volume_slider.setRange(0, 100)
        self.input_volume_slider.setValue(0) 
        self.input_volume_slider.valueChanged.connect(self.set_system_input_volume_qt)
        self.input_volume_label = QLabel(f"0%")
        self.input_volume_label.setAlignment(Qt.AlignCenter)
        input_slider_layout.addWidget(self.input_volume_slider)
        input_slider_layout.addWidget(self.input_volume_label)
        input_group_box_layout.addLayout(input_slider_layout)

        # Input Mute Button
        self.input_mute_button = QPushButton("Mute Input")
        self.input_mute_button.setIcon(get_icon("unmute", widget_style=self.style()))
        self.input_mute_button.setCheckable(True)
        self.input_mute_button.setChecked(False) # Assume not muted initially
        self.input_mute_button.toggled.connect(self.toggle_input_mute_qt)
        input_group_box_layout.addWidget(self.input_mute_button)

        self.input_device_layout = QVBoxLayout()
        self.input_device_button_group = QButtonGroup(self)
        self.input_device_button_group.setExclusive(True)
        self.input_device_button_group.buttonToggled.connect(self.change_audio_input_qt)
        input_group_box_layout.addLayout(self.input_device_layout)
        input_group_box_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)) # Spacer

        main_layout.addWidget(input_group_box)

        self.setLayout(main_layout)
        self.installEventFilter(self)

        # Timer to periodically refresh volume and device list
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_ui)
        self.refresh_timer.start(5000)

        # Initial population on startup
        self.refresh_ui() # Call refresh_ui once to populate everything

    def refresh_ui(self):
        """Refreshes both output and input device lists and volume statuses."""
        self.populate_output_devices_qt()
        self.update_output_volume_from_system_qt()
        self.populate_input_devices_qt()
        self.update_input_volume_from_system_qt()
        self.adjustSize() # Adjust widget size after populating devices

    # --- Output Device Control ---
    def set_system_output_volume_qt(self, value: int):
        """Sets system master volume for output from slider value (0-100)."""
        if self.current_output_audio_volume_ptr:
            set_master_volume_scalar(self.current_output_audio_volume_ptr, value / 100.0)
            self.output_volume_label.setText(f"{value}%")

    def update_output_volume_from_system_qt(self):
        """Updates the output slider and label from actual system volume of the current default output device."""
        default_endpoint_ptr = None
        try:
            default_endpoint_ptr = get_default_endpoint(self.enumerator_ptr, EDataFlow_eRender, ERole_eConsole)
            if default_endpoint_ptr:
                if self.current_output_audio_volume_ptr:
                    release_com_object(self.current_output_audio_volume_ptr)
                    self.current_output_audio_volume_ptr = None
                
                self.current_output_audio_volume_ptr = activate_audio_endpoint_volume(default_endpoint_ptr)
                
                current_volume_scalar = get_master_volume_scalar(self.current_output_audio_volume_ptr)
                current_volume_percent = int(current_volume_scalar * 100)
                
                self.output_volume_slider.blockSignals(True) 
                self.output_volume_slider.setValue(current_volume_percent)
                self.output_volume_slider.blockSignals(False)
                
                self.output_volume_label.setText(f"{current_volume_percent}%")

                is_muted = get_mute(self.current_output_audio_volume_ptr)
                self.output_mute_button.blockSignals(True)
                self.output_mute_button.setChecked(is_muted)
                self.output_mute_button.setIcon(get_icon("mute" if is_muted else "unmute", widget_style=self.style()))
                self.output_mute_button.setText("Unmute Output" if is_muted else "Mute Output")
                self.output_mute_button.blockSignals(False)

            else:
                self.output_volume_slider.setValue(0)
                self.output_volume_label.setText("N/A")
                self.current_output_audio_volume_ptr = None
                self.output_mute_button.blockSignals(True)
                self.output_mute_button.setChecked(False)
                self.output_mute_button.setIcon(get_icon("unmute", widget_style=self.style()))
                self.output_mute_button.setText("Mute Output")
                self.output_mute_button.blockSignals(False)
        except Exception as e:
            print(f"Error updating output volume from system: {e}")
            self.output_volume_slider.setValue(0)
            self.output_volume_label.setText("Error")
            self.current_output_audio_volume_ptr = None
        finally:
            release_com_object(default_endpoint_ptr)

    def toggle_output_mute_qt(self, checked):
        if self.current_output_audio_volume_ptr:
            set_mute(self.current_output_audio_volume_ptr, checked)
            self.output_mute_button.setIcon(get_icon("mute" if checked else "unmute", widget_style=self.style()))
            self.output_mute_button.setText("Unmute Output" if checked else "Mute Output")
            self.update_output_volume_from_system_qt() # Refresh volume to ensure consistency

    def populate_output_devices_qt(self):
        # Clear existing device buttons and labels
        for i in reversed(range(self.output_device_layout.count())):
            widget_to_remove = self.output_device_layout.itemAt(i).widget()
            if widget_to_remove:
                if isinstance(widget_to_remove, QAbstractButton):
                    self.output_device_button_group.removeButton(widget_to_remove)
                self.output_device_layout.removeWidget(widget_to_remove)
                widget_to_remove.deleteLater()

        devices = enumerate_audio_endpoints(self.enumerator_ptr, EDataFlow_eRender)
        current_default_id = None
        default_endpoint_ptr_temp = None 
        try:
            default_endpoint_ptr_temp = get_default_endpoint(self.enumerator_ptr, EDataFlow_eRender, ERole_eConsole)
            if default_endpoint_ptr_temp:
                current_default_id = get_device_id(default_endpoint_ptr_temp)
        except Exception as e:
            print(f"Could not get current default output device ID: {e}")
        finally:
            release_com_object(default_endpoint_ptr_temp)

        self.output_device_button_group.blockSignals(True)

        if devices:
            headphone_icon = get_icon("headphone", widget_style=self.style())
            for device in devices:
                radio_button = QRadioButton(device["name"])
                radio_button.setProperty("device_id", device["id"])
                radio_button.setProperty("device_ptr", device["ptr"])
                radio_button.setIcon(headphone_icon)
                self.output_device_layout.addWidget(radio_button)
                self.output_device_button_group.addButton(radio_button)

                if device["id"] == current_default_id:
                    radio_button.setChecked(True)
        else:
            no_devices_label = QLabel("No active output devices found.")
            self.output_device_layout.addWidget(no_devices_label)

        self.output_device_button_group.blockSignals(False)

    def change_audio_output_qt(self, button: QRadioButton, checked: bool):
        if checked:
            device_ptr_to_switch = button.property("device_ptr")
            if device_ptr_to_switch:
                try:
                    if switch_default_device(device_ptr_to_switch, EDataFlow_eRender):
                        if self.current_output_audio_volume_ptr:
                            release_com_object(self.current_output_audio_volume_ptr)
                            self.current_output_audio_volume_ptr = None
                        
                        new_default_endpoint_ptr = None
                        try:
                            new_default_endpoint_ptr = get_default_endpoint(self.enumerator_ptr, EDataFlow_eRender, ERole_eConsole)
                            if new_default_endpoint_ptr:
                                self.current_output_audio_volume_ptr = activate_audio_endpoint_volume(new_default_endpoint_ptr)
                                self.update_output_volume_from_system_qt()
                        finally:
                            release_com_object(new_default_endpoint_ptr)
                        
                        self.populate_output_devices_qt() 
                    else:
                        QMessageBox.warning(self, "Switch Failed", 
                                             "Failed to set default audio output device for any role.\n"
                                             "This might require administrator privileges or the device may not support the default roles.")
                        self.populate_output_devices_qt()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to switch default output device: {e}\n"
                                         "You might need to run the application as Administrator.")
                    self.populate_output_devices_qt()

    # --- Input Device Control ---
    def set_system_input_volume_qt(self, value: int):
        """Sets system master volume for input from slider value (0-100)."""
        if self.current_input_audio_volume_ptr:
            set_master_volume_scalar(self.current_input_audio_volume_ptr, value / 100.0)
            self.input_volume_label.setText(f"{value}%")

    def update_input_volume_from_system_qt(self):
        """Updates the input slider and label from actual system volume of the current default input device."""
        default_endpoint_ptr = None
        try:
            default_endpoint_ptr = get_default_endpoint(self.enumerator_ptr, EDataFlow_eCapture, ERole_eCommunications)
            if default_endpoint_ptr:
                if self.current_input_audio_volume_ptr:
                    release_com_object(self.current_input_audio_volume_ptr)
                    self.current_input_audio_volume_ptr = None
                
                self.current_input_audio_volume_ptr = activate_audio_endpoint_volume(default_endpoint_ptr)
                
                current_volume_scalar = get_master_volume_scalar(self.current_input_audio_volume_ptr)
                current_volume_percent = int(current_volume_scalar * 100)
                
                self.input_volume_slider.blockSignals(True) 
                self.input_volume_slider.setValue(current_volume_percent)
                self.input_volume_slider.blockSignals(False)
                
                self.input_volume_label.setText(f"{current_volume_percent}%")

                is_muted = get_mute(self.current_input_audio_volume_ptr)
                self.input_mute_button.blockSignals(True)
                self.input_mute_button.setChecked(is_muted)
                self.input_mute_button.setIcon(get_icon("mute" if is_muted else "unmute", widget_style=self.style()))
                self.input_mute_button.setText("Unmute Input" if is_muted else "Mute Input")
                self.input_mute_button.blockSignals(False)

            else:
                self.input_volume_slider.setValue(0)
                self.input_volume_label.setText("N/A")
                self.current_input_audio_volume_ptr = None
                self.input_mute_button.blockSignals(True)
                self.input_mute_button.setChecked(False)
                self.input_mute_button.setIcon(get_icon("unmute", widget_style=self.style()))
                self.input_mute_button.setText("Mute Input")
                self.input_mute_button.blockSignals(False)
        except Exception as e:
            print(f"Error updating input volume from system: {e}")
            self.input_volume_slider.setValue(0)
            self.input_volume_label.setText("Error")
            self.current_input_audio_volume_ptr = None
        finally:
            release_com_object(default_endpoint_ptr)

    def toggle_input_mute_qt(self, checked):
        if self.current_input_audio_volume_ptr:
            set_mute(self.current_input_audio_volume_ptr, checked)
            self.input_mute_button.setIcon(get_icon("mute" if checked else "unmute", widget_style=self.style()))
            self.input_mute_button.setText("Unmute Input" if checked else "Mute Input")
            self.update_input_volume_from_system_qt() # Refresh volume to ensure consistency

    def populate_input_devices_qt(self):
        # Clear existing device buttons and labels
        for i in reversed(range(self.input_device_layout.count())):
            widget_to_remove = self.input_device_layout.itemAt(i).widget()
            if widget_to_remove:
                if isinstance(widget_to_remove, QAbstractButton):
                    self.input_device_button_group.removeButton(widget_to_remove)
                self.input_device_layout.removeWidget(widget_to_remove)
                widget_to_remove.deleteLater()

        devices = enumerate_audio_endpoints(self.enumerator_ptr, EDataFlow_eCapture)
        current_default_id = None
        default_endpoint_ptr_temp = None 
        try:
            default_endpoint_ptr_temp = get_default_endpoint(self.enumerator_ptr, EDataFlow_eCapture, ERole_eCommunications)
            if default_endpoint_ptr_temp:
                current_default_id = get_device_id(default_endpoint_ptr_temp)
        except Exception as e:
            print(f"Could not get current default input device ID: {e}")
        finally:
            release_com_object(default_endpoint_ptr_temp)

        self.input_device_button_group.blockSignals(True)

        if devices:
            microphone_icon = get_icon("microphone", widget_style=self.style())
            for device in devices:
                radio_button = QRadioButton(device["name"])
                radio_button.setProperty("device_id", device["id"])
                radio_button.setProperty("device_ptr", device["ptr"])
                radio_button.setIcon(microphone_icon)
                self.input_device_layout.addWidget(radio_button)
                self.input_device_button_group.addButton(radio_button)

                if device["id"] == current_default_id:
                    radio_button.setChecked(True)
        else:
            no_devices_label = QLabel("No active input devices found.")
            self.input_device_layout.addWidget(no_devices_label)

        self.input_device_button_group.blockSignals(False)

    def change_audio_input_qt(self, button: QRadioButton, checked: bool):
        if checked:
            device_ptr_to_switch = button.property("device_ptr")
            if device_ptr_to_switch:
                try:
                    if switch_default_device(device_ptr_to_switch, EDataFlow_eCapture):
                        if self.current_input_audio_volume_ptr:
                            release_com_object(self.current_input_audio_volume_ptr)
                            self.current_input_audio_volume_ptr = None
                        
                        new_default_endpoint_ptr = None
                        try:
                            new_default_endpoint_ptr = get_default_endpoint(self.enumerator_ptr, EDataFlow_eCapture, ERole_eCommunications)
                            if new_default_endpoint_ptr:
                                self.current_input_audio_volume_ptr = activate_audio_endpoint_volume(new_default_endpoint_ptr)
                                self.update_input_volume_from_system_qt()
                        finally:
                            release_com_object(new_default_endpoint_ptr)
                        
                        self.populate_input_devices_qt() 
                    else:
                        QMessageBox.warning(self, "Switch Failed", 
                                             "Failed to set default audio input device for any role.\n"
                                             "This might require administrator privileges or the device may not support the default roles.")
                        self.populate_input_devices_qt()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to switch default input device: {e}\n"
                                         "You might need to run the application as Administrator.")
                    self.populate_input_devices_qt()

    def eventFilter(self, obj, event):
        if obj == self and event.type() == QEvent.WindowDeactivate:
            self.hide()
        return super().eventFilter(obj, event)

# --- New FloatingIcon Widget ---
class FloatingIcon(QWidget):
    clicked_to_show_widget = pyqtSignal() # Custom signal to notify parent to show volume widget

    def update_icon_pixmap(self):
        """Updates the pixmap of the icon_label based on current_icon_size."""
        self.icon_label.setPixmap(QIcon(self.icon_path).pixmap(QSize(self.current_icon_size, self.current_icon_size)))
        self.setFixedSize(self.current_icon_size, self.current_icon_size) # Update widget size

    def __init__(self, icon_path, initial_x, initial_y, icon_size, parent=None): # Added icon_size
        super().__init__(parent)
        # Removed Qt.WindowStaysOnTopHint so it can go behind other windows
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool) 
        self.setAttribute(Qt.WA_TranslucentBackground) # Make background transparent

        self.icon_path = icon_path # Store icon path to re-apply on size change
        self.current_icon_size = icon_size # Store current icon size

        self.icon_label = QLabel(self)
        self.update_icon_pixmap() # Call a method to set pixmap based on size
        self.icon_label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addWidget(self.icon_label)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.setGeometry(initial_x, initial_y, icon_size, icon_size) # Set initial size and position

        self.dragging = False
        self.offset = QPoint()
        self.click_pos = QPoint() # Store click position to differentiate click from drag

    def set_size(self, new_size):
        """Sets a new size for the icon and updates its pixmap."""
        if self.current_icon_size != new_size:
            self.current_icon_size = new_size
            self.update_icon_pixmap()
            # Reposition the icon to avoid jumping too much, try to keep its center
            current_center = self.geometry().center()
            new_x = current_center.x() - new_size // 2
            new_y = current_center.y() - new_size // 2
            self.move(new_x, new_y)
            
            app_instance = QApplication.instance()
            if hasattr(app_instance, 'save_icon_position'):
                app_instance.save_icon_position(self.x(), self.y()) # Save new position after resize


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.pos()
            self.click_pos = event.globalPos() # Store global position of click
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(self.mapToParent(event.pos() - self.offset))
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            # Check if the mouse moved significantly to differentiate drag from click
            if (event.globalPos() - self.click_pos).manhattanLength() < QApplication.startDragDistance():
                self.clicked_to_show_widget.emit()
            event.accept()

        app_instance = QApplication.instance()
        if hasattr(app_instance, 'save_icon_position'):
            app_instance.save_icon_position(self.x(), self.y())


class SystemTrayApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)

        # Set Dark Mode Palette
        self.setStyle("Fusion")
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
        dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(128, 128, 128))
        dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(128, 128, 128))
        self.setPalette(dark_palette)


        # Initialize COM and get device enumerator once
        try:
            init_com()
            self.device_enumerator_ptr = create_device_enumerator()
        except Exception as e:
            QMessageBox.critical(None, "Initialization Error", f"Failed to initialize audio system: {e}\n"
                                 "Please ensure your audio drivers are working and try running as Administrator.")
            sys.exit(1)

        # Load initial config
        self.config_settings = load_config()
        self.floating_widget_enabled = self.config_settings['toggle']
        self.preferred_monitor_index = self.config_settings['monitor']
        self.icon_x = self.config_settings['icon_x']
        self.icon_y = self.config_settings['icon_y']
        self.icon_size = self.config_settings['icon_size'] # Load icon size

        # Create the floating volume widget instance
        self.floating_volume_widget = FloatingVolumeWidget(self.device_enumerator_ptr)
        
        # Create the draggable floating icon
        self.floating_icon_widget = FloatingIcon(os.path.join(base_path, "outputcontrol_icon.ico"), 
                                                 self.icon_x, self.icon_y, self.icon_size) # Pass icon_size
        self.floating_icon_widget.clicked_to_show_widget.connect(self.show_floating_widget_from_icon)


        # Try to load tray icon from the bundled .ico file
        try:
            self.tray_icon = QSystemTrayIcon(QIcon(os.path.join(base_path, "outputcontrol_icon.ico")))
        except Exception:
            self.tray_icon = QSystemTrayIcon(QIcon())
            QMessageBox.warning(None, "Icon Missing", "outputcontrol_icon.ico not found. Please place it in the same directory or bundle correctly.")
            
        self.tray_icon.setToolTip("OutputControl")

        # --- Tray Menu Setup ---
        menu = QMenu()

        # Toggle Floating Widget Action
        self.toggle_widget_action = QAction("Toggle Floating Icon", menu, checkable=True)
        self.toggle_widget_action.setChecked(self.floating_widget_enabled)
        self.toggle_widget_action.triggered.connect(self.toggle_floating_widget)
        menu.addAction(self.toggle_widget_action)

        # Icon Size Submenu
        icon_size_menu = QMenu("Icon Size", menu)
        self.icon_size_action_group = QActionGroup(self)
        self.icon_size_action_group.setExclusive(True)

        sizes = {"Small": 32, "Medium": 48, "Large": 64}
        for name, size in sizes.items():
            action = QAction(name, icon_size_menu, checkable=True)
            action.setData(size)
            action.triggered.connect(lambda checked, s=size: self.set_icon_size(s))
            icon_size_menu.addAction(action)
            self.icon_size_action_group.addAction(action)
            if size == self.icon_size:
                action.setChecked(True)
        menu.addMenu(icon_size_menu)
        menu.addSeparator()

        # Monitor Selection Submenu
        monitor_menu = QMenu("Select Monitor", menu)
        
        self.monitor_action_group = QActionGroup(self)
        self.monitor_action_group.setExclusive(True)

        desktop = QApplication.desktop()
        num_screens = desktop.screenCount()
        self.monitor_actions = []

        for i in range(num_screens):
            screen_name = f"Monitor {i + 1}"
            screen_geometry = desktop.screenGeometry(i)
            action = QAction(f"{screen_name} ({screen_geometry.width()}x{screen_geometry.height()})", monitor_menu, checkable=True)
            action.setData(i + 1)
            
            action.triggered.connect(lambda checked, act=action: self.set_monitor(act.data()))
            
            monitor_menu.addAction(action)
            self.monitor_action_group.addAction(action)
            self.monitor_actions.append(action)

            if (i + 1) == self.preferred_monitor_index:
                action.setChecked(True)
        
        menu.addMenu(monitor_menu)
        menu.addSeparator()

        # Quit Action
        quit_action = QAction("Quit", menu)
        transparent_pixmap = QPixmap(1, 1)
        transparent_pixmap.fill(Qt.transparent)
        transparent_icon = QIcon(transparent_pixmap)
        quit_action.setIcon(transparent_icon)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)

        self.tray_icon.activated.connect(self.tray_icon_activated)

        self.tray_icon.show()

        # Connect cleanup method to application quit signal
        self.aboutToQuit.connect(self._cleanup_com)

        # Show floating icon initially if enabled in config
        if self.floating_widget_enabled:
            self.floating_icon_widget.show()

    def _cleanup_com(self):
        """
        Releases the main COM enumerator and explicitly deletes top-level widgets.
        This method is called when the application is about to quit.
        """
        print("Cleaning up COM objects and widgets...")
        if self.device_enumerator_ptr:
            release_com_object(self.device_enumerator_ptr)
            self.device_enumerator_ptr = None
            print("Released device enumerator COM object.")
        
        # Explicitly delete top-level widgets.
        # While QApplication's destructor usually handles this, explicit calls
        # can prevent subtle issues in complex shutdown scenarios.
        if self.floating_volume_widget:
            self.floating_volume_widget.deleteLater()
            self.floating_volume_widget = None
            print("Scheduled FloatingVolumeWidget for deletion.")
        
        if self.floating_icon_widget:
            self.floating_icon_widget.deleteLater()
            self.floating_icon_widget = None
            print("Scheduled FloatingIcon for deletion.")


    # Helper method to save icon position from FloatingIcon
    def save_icon_position(self, x, y):
        self.icon_x = x
        self.icon_y = y
        save_config(self.floating_widget_enabled, self.preferred_monitor_index, self.icon_x, self.icon_y, self.icon_size)

    def toggle_floating_widget(self, checked):
        self.floating_widget_enabled = checked
        save_config(self.floating_widget_enabled, self.preferred_monitor_index, self.icon_x, self.icon_y, self.icon_size)
        if self.floating_widget_enabled:
            self.floating_icon_widget.show()
        else:
            self.floating_icon_widget.hide()
            self.floating_volume_widget.hide() # Also hide the volume widget if icon is disabled

    def set_icon_size(self, size):
        self.icon_size = size
        self.floating_icon_widget.set_size(size) # Update the floating icon widget's size
        save_config(self.floating_widget_enabled, self.preferred_monitor_index, self.icon_x, self.icon_y, self.icon_size)

    def set_monitor(self, monitor_idx):
        self.preferred_monitor_index = monitor_idx
        save_config(self.floating_widget_enabled, self.preferred_monitor_index, self.icon_x, self.icon_y, self.icon_size)
        
        # If floating icon is visible, reposition it relative to the new monitor
        if self.floating_icon_widget.isVisible():
            desktop = QApplication.desktop()
            target_screen_index = self.preferred_monitor_index - 1
            if not (0 <= target_screen_index < desktop.screenCount()):
                target_screen_index = 0
                self.preferred_monitor_index = 1
                save_config(self.floating_widget_enabled, self.preferred_monitor_index, self.icon_x, self.icon_y, self.icon_size)

            screen_geometry = desktop.screenGeometry(target_screen_index)
            
            # Reposition the icon to a default spot on the new monitor
            new_x = screen_geometry.x() + screen_geometry.width() - self.floating_icon_widget.width() - 50
            new_y = screen_geometry.y() + screen_geometry.height() - self.floating_icon_widget.height() - 50
            self.floating_icon_widget.move(new_x, new_y)
            self.save_icon_position(new_x, new_y)

        if self.floating_volume_widget.isVisible():
            # If the volume widget is already visible, reposition it based on the new monitor setting
            # This call will use the floating icon's position as reference
            self.show_floating_widget_from_icon() 

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            # When tray icon is left-clicked, show the volume widget on the current cursor's monitor.
            self.show_floating_widget_from_tray_click()
        elif reason == QSystemTrayIcon.Context:
            pass # Context menu is handled by setContextMenu

    def show_floating_widget_from_icon(self):
        """
        Shows the FloatingVolumeWidget, positioned relative to the FloatingIcon.
        This method is triggered by the FloatingIcon's clicked_to_show_widget signal.
        """
        self.floating_volume_widget.refresh_ui()

        icon_rect = self.floating_icon_widget.geometry()
        
        # Calculate dynamic height based on number of devices
        num_output_devices = len(enumerate_audio_endpoints(self.device_enumerator_ptr, EDataFlow_eRender))
        num_input_devices = len(enumerate_audio_endpoints(self.device_enumerator_ptr, EDataFlow_eCapture))
        
        device_item_height = 25 
        base_widget_height = 180 
        window_height = base_widget_height + (num_output_devices * device_item_height) + (num_input_devices * device_item_height)
        window_width = 280 

        desktop = QApplication.desktop()
        current_screen_index = desktop.screenNumber(icon_rect.center())
        screen_available_geometry = desktop.availableGeometry(current_screen_index)

        # Determine if the icon is on the left or right half of the available screen
        screen_center_x = screen_available_geometry.x() + screen_available_geometry.width() / 2

        # Initial positioning attempts
        # Try right first if icon is on left half, or left if icon is on right half
        if icon_rect.center().x() < screen_center_x:
            # Icon is on the left half, try to display widget to the right
            target_x = icon_rect.right() + 5
            target_y = icon_rect.center().y() - window_height // 2
            
            # Check if it fits to the right
            if (target_x + window_width > screen_available_geometry.right() and
                icon_rect.left() - window_width - 5 >= screen_available_geometry.left()):
                # If it doesn't fit right, try left
                target_x = icon_rect.left() - window_width - 5
        else:
            # Icon is on the right half, try to display widget to the left
            target_x = icon_rect.left() - window_width - 110
            target_y = icon_rect.center().y() - window_height // 2

            # Check if it fits to the left
            if (target_x < screen_available_geometry.left() and
                icon_rect.right() + 5 + window_width <= screen_available_geometry.right()):
                # If it doesn't fit left, try right
                target_x = icon_rect.right() + 5
        
        target_y = target_y - 250

        # Ensure Y position is within bounds, adjusting if necessary
        if target_y < screen_available_geometry.top():
            target_y = screen_available_geometry.top()
        elif target_y + window_height > screen_available_geometry.bottom():
            target_y = screen_available_geometry.bottom() - window_height

        self.floating_volume_widget.setGeometry(target_x, target_y, window_width, window_height)

        self.floating_volume_widget.show()
        self.floating_volume_widget.activateWindow()
        self.floating_volume_widget.raise_()

    def show_floating_widget_from_tray_click(self):
        """
        Shows the FloatingVolumeWidget, positioned centered horizontally on the mouse
        and with its bottom edge above the mouse, ensuring it appears above the taskbar.
        """
        self.floating_volume_widget.refresh_ui()

        desktop = QApplication.desktop()
        cursor_pos = QCursor.pos() # Get current mouse cursor global position
        current_screen_index = desktop.screenNumber(cursor_pos)
        screen_available_geometry = desktop.availableGeometry(current_screen_index)

        window_width = 280
        num_output_devices = len(enumerate_audio_endpoints(self.device_enumerator_ptr, EDataFlow_eRender))
        num_input_devices = len(enumerate_audio_endpoints(self.device_enumerator_ptr, EDataFlow_eCapture))
        device_item_height = 25
        base_widget_height = 180
        window_height = base_widget_height + (num_output_devices * device_item_height) + (num_input_devices * device_item_height)

        # Fixed offset from the right edge of the available screen area
        # This will make it appear "further to the left" of the cursor's general area
        # Adjust 100 as needed to move it further left or right
        x_offset_from_right_edge = 200
        target_x = screen_available_geometry.right() - window_width - x_offset_from_right_edge

        # Fixed offset from the bottom edge of the available screen area (above taskbar)
        # Adjust 10 as needed for "further up" or down
        y_offset_from_bottom_edge = 75
        target_y = screen_available_geometry.bottom() - window_height - y_offset_from_bottom_edge

        # Boundary checks for x-position
        if target_x < screen_available_geometry.left():
            target_x = screen_available_geometry.left()
        elif target_x + window_width > screen_available_geometry.right():
            target_x = screen_available_geometry.right() - window_width

        # Boundary checks for y-position (already handled by fixed position relative to bottom)
        if target_y < screen_available_geometry.top():
            target_y = screen_available_geometry.top()

        self.floating_volume_widget.setGeometry(target_x, target_y, window_width, window_height)

        self.floating_volume_widget.show()
        self.floating_volume_widget.activateWindow()
        self.floating_volume_widget.raise_()


if __name__ == "__main__":
    app = SystemTrayApp(sys.argv)
    sys.exit(app.exec_())
