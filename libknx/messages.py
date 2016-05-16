"""KNXnet/IP message implementations required bny knxmap."""
import collections
import io
import logging
import socket
import struct

from .core import *

__all__ = ['get_message_type',
           'parse_message',
           'KnxSearchRequest',
           'KnxSearchResponse',
           'KnxDescriptionRequest',
           'KnxDescriptionResponse',
           'KnxConnectRequest',
           'KnxConnectResponse',
           'KnxTunnellingRequest',
           'KnxTunnellingAck',
           'KnxConnectionStateRequest',
           'KnxConnectionStateResponse',
           'KnxDisconnectRequest',
           'KnxDisconnectResponse']

LOGGER = logging.getLogger(__name__)


def get_message_type(message):
    try:
        header = {}
        header['header_length'], \
        header['protocol_version'], \
        header['service_type'], \
        header['total_length'] = struct.unpack('>BBHH', message[:6])
        message_type = int(header['service_type'])
    except Exception as e:
        LOGGER.exception(e)
        return
    return message_type


def parse_message(data):
    message_type = get_message_type(data)
    if message_type == 0x0206:  # CONNECT_RESPONSE
        LOGGER.debug('Parsing KnxConnectResponse')
        return KnxConnectResponse(data)
    elif message_type == 0x0420:  # TUNNELLING_REQUEST
        return KnxTunnellingRequest(data)
    elif message_type == 0x0421:  # TUNNELLING_ACK
        LOGGER.debug('Parsing KnxTunnelingAck')
        return KnxTunnellingAck(data)
    elif message_type == 0x0207: # CONNECTIONSTATE_REQUEST
        LOGGER.debug('Parsing KnxConnectionStateRequest')
        return KnxConnectionStateRequest(data)
    elif message_type == 0x0208:  # CONNECTIONSTATE_RESPONSE
        LOGGER.debug('Parsing KnxConnectionStateResponse')
        return KnxConnectionStateResponse(data)
    elif message_type == 0x0209:  # DISCONNECT_REQUEST
        LOGGER.debug('Parsing KnxDisconnectRequest')
        return KnxDisconnectRequest(data)
    elif message_type == 0x020a:  # DISCONNECT_RESPONSE
        LOGGER.debug('Parsing KnxDisconnectResponse')
        return KnxDisconnectResponse(data)
    else:
        LOGGER.error('Unknown message type: '.format(message_type))
        return


class KnxMessage(object):
    header = {
        'header_length': KNX_CONSTANTS['HEADER_SIZE_10'],
        'protocol_version': KNX_CONSTANTS['KNXNETIP_VERSION_10'],
        'service_type': None,
        'total_length': None}

    def __init__(self):
        self.body = collections.OrderedDict()
        self.message = None
        self.source = None
        self.port = None
        self.knx_source = None
        self.knx_destination = None

    @staticmethod
    def parse_knx_address(address):
        """Parse physical/individual KNX address.

        Address structure (A=Area, L=Line, B=Bus device):
        --------------------
        |AAAA|LLLL|BBBBBBBB|
        --------------------
        4 Bit|4 Bit| 8 Bit

        >>> parse_knx_address(99999)
        '8.6.159'
        """
        return '{}.{}.{}'.format((address >> 12) & 0xf, (address >> 8) & 0xf, address & 0xff)

    @staticmethod
    def pack_knx_address(address):
        """Pack physical/individual KNX address.

        >>> pack_knx_address('15.15.255')
        65535
        """
        parts = address.split('.')
        return (int(parts[0]) << 12) + (int(parts[1]) << 8) + (int(parts[2]))

    @staticmethod
    def parse_knx_group_address(address):
        """Parse KNX group address.

        >>> parse_knx_group_address(12345)
        '6/0/57'
        """
        return '{}/{}/{}'.format((address >> 11) & 0x1f, (address >> 8) & 0x7, address & 0xff)

    @staticmethod
    def pack_knx_group_address(address):
        """Pack KNX group address.

        >>> pack_knx_group_address('6/0/57')
        12345
        """
        parts = address.split('/')
        return (int(parts[0]) << 11) + (int(parts[1]) << 8) + (int(parts[2]))

    @staticmethod
    def parse_knx_device_serial(address):
        """Parse a KNX device serial to human readable format.

        >>> parse_knx_device_serial(b'\x00\x00\x00\x00\X12\x23')
        '000000005C58'
        """
        return '{0:02X}{1:02X}{2:02X}{3:02X}{4:02X}{5:02X}'.format(*address)

    @staticmethod
    def parse_mac_address(address):
        """Parse a MAC address to human readable format.

        >>> parse_mac_address(b'\x12\x34\x56\x78\x90\x12')
        '12:34:56:78:90:12'
        """
        return '{0:02X}:{1:02X}:{2:02X}:{3:02X}:{4:02X}:{5:02X}'.format(*address)

    def set_knx_destination(self, address):
        """Set the KNX destination address of a KnxMessage instance."""
        self.knx_destination = self.pack_knx_address(address)

    def get_message(self):
        """Return the current message."""
        # TODO: Maybe use this as string representation?
        return self.message if self.message else False

    def pack_knx_message(self):
        self.message = self._pack_knx_header()
        self.message += self._pack_knx_body()

    def unpack_knx_message(self, message):
        message = self._unpack_knx_header(message)
        self._unpack_knx_body(message)

    def _pack_knx_header(self):
        try:
            return struct.pack('!BBHH',
                               self.header.get('header_length'),
                               self.header.get('protocol_version'),
                               self.header.get('service_type'),
                               self.header.get('total_length'))
        except struct.error as e:
            print(e)

    def _unpack_knx_header(self, message):
        """Set self.header dict and return message body"""
        try:
            self.header['header_length'], \
            self.header['protocol_version'], \
            self.header['service_type'], \
            self.header['total_length'] = struct.unpack('!BBHH', message[:6])
            return message[6:]
        except struct.error as e:
            LOGGER.exception(e)

    def _pack_knx_body(self):
        """Subclasses must define this method."""
        raise NotImplementedError

    def _unpack_knx_body(self, message):
        """Subclasses must define this method."""
        raise NotImplementedError

    @staticmethod
    def _unpack_stream(fmt, stream):
        try:
            buf = stream.read(struct.calcsize(fmt))
            return struct.unpack(fmt, buf)[0]
        except struct.error as e:
            LOGGER.exception(e)

    def _parse_knx_body_hpai(self, message):
        try:
            self.body['hpai'] = dict()
            self.body['hpai']['structure_length'], \
            self.body['hpai']['protocol_code'], \
            self.body['hpai']['ip_address'], \
            self.body['hpai']['port'] = struct.unpack('!BBHH', message[:8])
            self.body['hpai']['ip_address'] = socket.inet_aton(self.body['hpai']['ip_address']) # most likely not works
            return message[8:]
        except struct.error as e:
            LOGGER.exception(e)

    def _pack_hpai(self):
        hpai = struct.pack('!B', 8) # structure_length
        hpai += struct.pack('!B', 0x01) # protocol code
        hpai += socket.inet_aton(self.source)
        hpai += struct.pack('!H', self.port)
        return hpai

    def _unpack_hpai(self, message):
        hpai = dict()
        hpai['structure_length'] = self._unpack_stream('!B', message)
        hpai['protocol_code'] = self._unpack_stream('!B', message)
        hpai['ip_address'] = socket.inet_ntoa(message.read(4))
        hpai['port'] = self._unpack_stream('!H', message)
        return hpai

    def _unpack_dib_dev_info(self, message):
        dib_dev_info = dict()
        dib_dev_info['structure_length'] = self._unpack_stream('!B', message)
        dib_dev_info['description_type'] = self._unpack_stream('!B', message)
        dib_dev_info['knx_medium'] = self._unpack_stream('!B', message)
        dib_dev_info['device_status'] = 'PROGMODE_ON' if self._unpack_stream('!B', message) else 'PROGMODE_OFF'
        dib_dev_info['knx_address'] = self.parse_knx_address(self._unpack_stream('!H', message))
        dib_dev_info['project_install_identifier'] = self._unpack_stream('!H', message)
        dib_dev_info['knx_device_serial'] = self.parse_knx_device_serial(
            self._unpack_stream('!6s', message))
        dib_dev_info['knx_dev_multicast_address'] = socket.inet_ntoa(message.read(4))
        dib_dev_info['knx_mac_address'] = self.parse_mac_address(self._unpack_stream('!6s', message))
        dib_dev_info['device_friendly_name'] = self._unpack_stream('!30s', message)
        return dib_dev_info

    def _unpack_dib_supp_sv_families(self, message):
        dib_supp_sv_families = collections.OrderedDict()
        dib_supp_sv_families['structure_length'] = self._unpack_stream('!B', message)
        dib_supp_sv_families['description_type'] = self._unpack_stream('!B', message)
        dib_supp_sv_families['families'] = {}

        for i in range(int((dib_supp_sv_families['structure_length'] - 2) / 2)):
            service_id = self._unpack_stream('!B', message)
            version = self._unpack_stream('!B', message)
            dib_supp_sv_families['families'][service_id] = dict()
            dib_supp_sv_families['families'][service_id]['version'] = version

        return dib_supp_sv_families

    def _pack_cemi(self):
        cemi = struct.pack('!B', self.cemi_message_code) # cEMI message code
        cemi += struct.pack('!B', 0) # add information length # TODO: implement variable length if additional information is included

        # See: http://www.openremote.org/display/knowledge/Common+EMI+Frame+Control+Fields
        #  Control Field 1
        #  Bit  |
        # ------+---------------------------------------------------------------
        #   7   | Frame Type  - 0x0 for extended frame
        #       |               0x1 for standard frame
        # ------+---------------------------------------------------------------
        #   6   | Reserved
        #       |
        # ------+---------------------------------------------------------------
        #   5   | Repeat Flag - 0x0 repeat frame on medium in case of an error
        #       |               0x1 do not repeat
        # ------+---------------------------------------------------------------
        #   4   | System Broadcast - 0x0 system broadcast
        #       |                    0x1 broadcast
        # ------+---------------------------------------------------------------
        #   3   | Priority    - 0x0 system
        #       |               0x1 normal
        # ------+               0x2 urgent
        #   2   |               0x3 low
        #       |
        # ------+---------------------------------------------------------------
        #   1   | Acknowledge Request - 0x0 no ACK requestedhttp://www.weinzierl.de/images/development/images/development/net_n_node/1.png
        #       | (L_Data.req)          0x1 ACK requested
        # ------+---------------------------------------------------------------
        #   0   | Confirm      - 0x0 no error
        #       | (L_Data.con) - 0x1 error
        # ------+---------------------------------------------------------------
        #
        #
        # Control Field 2
        #
        #  Bit  |
        # ------+---------------------------------------------------------------
        #   7   | Destination Address Type - 0x0 individual address
        #       |                          - 0x1 group address
        # ------+---------------------------------------------------------------
        #  6-4  | Hop Count (0-7)
        # ------+---------------------------------------------------------------
        #  3-0  | Extended Frame Format - 0x0 standard frame
        # ------+---------------------------------------------------------------


        def set_bit(value, bit):
            return value | (1 << bit)

        def clear_bit(value, bit):
            return value & ~(1 << bit)

        def is_set_bit(value, pos):
            if (value&(2**pos)) is not 0:
                return True
            else:
                return False

        def gen_cf1():
            cf = 0
            cf = clear_bit(cf, 0) # confirm (no error)
            cf = clear_bit(cf, 1) # acknowledge request (no ACK)
            cf = clear_bit(cf, 2) # system
            cf = clear_bit(cf, 3) # system
            cf = set_bit(cf, 4) # broadcast
            cf = set_bit(cf, 5) # repeat if error
            cf = clear_bit(cf, 6) # reserved
            cf = set_bit(cf, 7) # standard frame
            return cf

        def gen_cf2():
            cf = 0
            cf = clear_bit(cf, 0) # standard frame
            cf = clear_bit(cf, 1)
            cf = clear_bit(cf, 2)
            cf = clear_bit(cf, 3)
            cf = clear_bit(cf, 4) # hop count (6)
            cf = set_bit(cf, 5)
            cf = set_bit(cf, 6)
            cf = clear_bit(cf, 7) # address type (group address)
            return cf

        cemi += struct.pack('!B', gen_cf1()) # controlfield 1
        cemi += struct.pack('!B', gen_cf2()) # controlfield 2
        cemi += struct.pack('!H', self.knx_source) # source address (KNX address)
        cemi += struct.pack('!H', self.knx_destination) # KNX destination address (either group or physical)

        cemi += struct.pack('!B', 0x01) # Data length
        #cemi += struct.pack('!H', 0x0081) # Application Protocol Data Unit (APDU) - the actual payload (TPCI, APCI)
        cemi += struct.pack('!H', 0x0300)  # Application Protocol Data Unit (APDU) - the actual payload (TPCI, APCI)
        return cemi

    def _unpack_cemi(self, message):
        cemi = dict()
        cemi['message_code'] = self._unpack_stream('!B', message)
        cemi['information_length'] = self._unpack_stream('!B', message)
        if cemi['information_length'] is 0:
            cemi['controlfield_1'] = self._unpack_stream('!B', message)
            cemi['controlfield_2'] = self._unpack_stream('!B', message)
            cemi['knx_source'] = self._unpack_stream('!H', message)
            cemi['knx_destination'] = self._unpack_stream('!H', message)
            cemi['npdu'] = self._unpack_stream('!B', message)
            cemi['tcpi'] = self._unpack_stream('!B', message)
            cemi['apci'] = self._unpack_stream('!B', message)
        else:
            cemi['additional_information'] = {}
            cemi['additional_information']['busmonitor_info'] = self._unpack_stream('!B', message)
            cemi['additional_information']['busmonitor_info_length'] = self._unpack_stream('!B', message)
            cemi['additional_information']['busmonitor_info_error_flags'] = self._unpack_stream('!B', message)
            cemi['additional_information']['extended_relative_timestamp'] = self._unpack_stream('!B', message)
            cemi['additional_information']['extended_relative_timestamp'] = self._unpack_stream('!B', message)
            cemi['additional_information']['extended_relative_timestamp'] = self._unpack_stream('!I', message)
            cemi['raw_frame'] = message.read()
        return cemi


class KnxSearchRequest(KnxMessage):

    def __init__(self, message=None, sockname=None):
        super(KnxSearchRequest, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0201
            self.header['total_length'] = 14
            try:
                self.source, self.port = sockname
                self.pack_knx_message()
            except TypeError:
                self.source = None
                self.port = None

    def _pack_knx_body(self):
        self.body = self._pack_hpai()
        return self.body

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body = self._unpack_hpai(message)
        except Exception as e:
            LOGGER.exception(e)


class KnxSearchResponse(KnxMessage):

    def __init__(self, message=None):
        super(KnxSearchResponse, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0202
            self.pack_knx_message()

    def _pack_knx_body(self):
        raise NotImplementedError

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body = self._unpack_hpai(message)
            self.body['dib_dev_info'] = self._unpack_dib_dev_info(message)
            self.body['dib_supp_sv_families'] = self._unpack_dib_supp_sv_families(message)
        except Exception as e:
            LOGGER.exception(e)


class KnxDescriptionRequest(KnxMessage):

    def __init__(self, message=None, sockname=None):
        super(KnxDescriptionRequest, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0203
            self.header['total_length'] = 14
            try:
                self.source, self.port = sockname
                self.pack_knx_message()
            except TypeError:
                self.source = None
                self.port = None

    def _pack_knx_body(self):
        self.body = self._pack_hpai()
        return self.body

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body = self._unpack_hpai(message)
        except Exception as e:
            LOGGER.exception(e)


class KnxDescriptionResponse(KnxMessage):

    def __init__(self, message=None):
        super(KnxDescriptionResponse, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0204
            self.pack_knx_message()

    def _pack_knx_body(self):
        raise NotImplementedError

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body['dib_dev_info'] = self._unpack_dib_dev_info(message)
            self.body['dib_supp_sv_families'] = self._unpack_dib_supp_sv_families(message)
        except Exception as e:
            LOGGER.exception(e)


class KnxConnectRequest(KnxMessage):
    layer_types = {
        0x02: 'TUNNEL_LINKLAYER',
        0x03: 'DEVICE_MGMT_CONNECTION',
        0x04: 'TUNNEL_RAW',
        0x06: 'REMLOG_CONNECTION',
        0x07: 'REMCONF_CONNECTION',
        0x08: 'OBJSVR_CONNECTION',
        0x80: 'TUNNEL_BUSMONITOR'}

    def __init__(self, message=None, sockname=None, layer_type=0x02):
        super(KnxConnectRequest, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0205
            self.header['total_length'] = 26
            self.layer_type = layer_type
            try:
                self.source, self.port = sockname
                self.pack_knx_message()
            except TypeError:
                self.source = None
                self.port = None

    def _pack_knx_body(self):
        # Discovery endpoint
        self.body = self._pack_hpai()
        # Data endpoint
        self.body += self._pack_hpai()
        # Connection request information
        self.body += struct.pack('!B', 4)  # structure_length
        self.body += struct.pack('!B', 0x04)  # connection type # TODO: implement other connections (routing, object server)
        self.body += struct.pack('!B', self.layer_type)  # knx layer type
        self.body += struct.pack('!B', 0x00)  # reserved
        return self.body

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            # Discovery endpoint
            self.body = self._unpack_hpai(message)
            # Data endpoint
            self.body['data_endpoint'] = self._unpack_hpai(message)
            # Connection request information
            self.body['connection_request_information'] = dict()
            self.body['connection_request_information']['structure_length'] = self._unpack_stream('!B', message)
            self.body['connection_request_information']['connection_type'] = self._unpack_stream('!B', message)
            self.body['connection_request_information']['knx_layer'] = self._unpack_stream('!B', message)
            self.body['connection_request_information']['reserved'] = self._unpack_stream('!B', message)
        except Exception as e:
            LOGGER.exception(e)


class KnxConnectResponse(KnxMessage):
    ERROR = None
    ERROR_CODE = None

    def __init__(self, message=None):
        super(KnxConnectResponse, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0206
            self.header['total_length'] = 20
            self.pack_knx_message()

    def _pack_knx_body(self):
        raise NotImplementedError

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body['communication_channel_id'] = self._unpack_stream('!B', message)
            self.body['status'] = self._unpack_stream('!B', message)

            if self.body['status'] != 0x00:
                # TODO: implement some kind of retries and waiting periods
                self.ERROR = KNX_STATUS_CODES[self.body['status']]
                self.ERROR_CODE = self.body['status']
                return

            self.body['hpai'] = self._unpack_hpai(message)
            # Connection response data block
            self.body['data_block'] = dict()
            self.body['data_block']['structure_length'] = self._unpack_stream('!B', message)
            self.body['data_block']['connection_type'] = self._unpack_stream('!B', message)
            self.body['data_block']['knx_address'] = self.parse_knx_address(self._unpack_stream('!H', message))
        except Exception as e:
            LOGGER.exception(e)


class KnxTunnellingRequest(KnxMessage):

    def __init__(self, message=None, sockname=None, communication_channel=None,
                 knx_source=None, knx_destination=None, sequence_count=0, message_code=0x11):
        super(KnxTunnellingRequest, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0420
            self.header['total_length'] = 21
            self.communication_channel = communication_channel
            self.sequence_count = sequence_count
            self.cemi_message_code = message_code
            if knx_source:
                self.knx_source = self.pack_knx_address(knx_source)
            else:
                self.knx_source = self.pack_knx_address('0.0.0') # TODO: only for dev, will be removed

            if knx_destination:
                self.set_knx_destination(knx_destination)

            try:
                self.source, self.port = sockname
                self.pack_knx_message()
            except TypeError:
                self.source = None
                self.port = None

    def _pack_knx_body(self):
        self.body = struct.pack('!B', 4) # structure_length
        self.body += struct.pack('!B', self.communication_channel) # channel id
        self.body += struct.pack('!B', self.sequence_count) # sequence counter
        self.body += struct.pack('!B', 0) # reserved
        # cEMI
        self.body += self._pack_cemi()
        return self.body

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body['structure_length'] = self._unpack_stream('!B', message)
            self.body['communication_channel_id'] = self._unpack_stream('!B', message)
            self.body['sequence_counter'] = self._unpack_stream('!B', message)
            self.body['reserved'] = self._unpack_stream('!B', message)
            # cEMI
            self.body['cemi'] = self._unpack_cemi(message)
        except Exception as e:
            LOGGER.exception(e)


class KnxTunnellingAck(KnxMessage):

    def __init__(self, message=None, communication_channel=None, sequence_count=0):
        super(KnxTunnellingAck, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0421
            self.header['total_length'] = 10
            self.communication_channel = communication_channel
            self.sequence_count = sequence_count
            self.pack_knx_message()

    def _pack_knx_body(self):
        self.body = struct.pack('!B', 4) # structure_length
        self.body += struct.pack('!B', self.communication_channel) # channel id
        self.body += struct.pack('!B', self.sequence_count) # sequence counter
        self.body += struct.pack('!B', 0) # status
        return self.body

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body['structure_length'] = self._unpack_stream('!B', message)
            self.body['communication_channel_id'] = self._unpack_stream('!B', message)
            self.body['sequence_counter'] = self._unpack_stream('!B', message)
            self.body['status'] = self._unpack_stream('!B', message)
        except Exception as e:
            LOGGER.exception(e)


class KnxConnectionStateRequest(KnxMessage):

    def __init__(self, message=None, sockname=None, communication_channel=None,
                 knx_source=None, knx_destination=None):
        super(KnxConnectionStateRequest, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0207
            self.header['total_length'] = 16
            self.communication_channel = communication_channel
            try:
                self.source, self.port = sockname
                self.pack_knx_message()
            except TypeError:
                self.source = None
                self.port = None

    def _pack_knx_body(self):
        self.body = struct.pack('!B', self.communication_channel) # channel id
        self.body += struct.pack('!B', 0) # reserved
        # HPAI
        self.body += self._pack_hpai()
        return self.body

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body['communication_channel_id'] = self._unpack_stream('!B', message)
            self.body['reserved'] = self._unpack_stream('!B', message)
            # HPAI
            self.body['hpai'] = self._unpack_hpai(message)
        except Exception as e:
            LOGGER.exception(e)


class KnxConnectionStateResponse(KnxMessage):

    def __init__(self, message=None, communication_channel=None,
                 knx_source=None, knx_destination=None):
        super(KnxConnectionStateResponse, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0208
            self.header['total_length'] = 8
            self.communication_channel = communication_channel
            self.pack_knx_message()

    def _pack_knx_body(self):
        # discovery endpoint
        self.body = struct.pack('!B', self.communication_channel)  # channel id
        self.body += struct.pack('!B', 0)  # status
        return self.body

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body['communication_channel_id'] = self._unpack_stream('!B', message)
            self.body['status'] = self._unpack_stream('!B', message)
        except Exception as e:
            LOGGER.exception(e)


class KnxDisconnectRequest(KnxMessage):

    def __init__(self, message=None, sockname=None, communication_channel=None,
                 knx_source=None, knx_destination=None):
        super(KnxDisconnectRequest, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x0209
            self.header['total_length'] = 16
            self.communication_channel = communication_channel
            try:
                self.source, self.port = sockname
                self.pack_knx_message()
            except TypeError:
                self.source = None
                self.port = None

    def _pack_knx_body(self):
        self.body = struct.pack('!B', self.communication_channel) # channel id
        self.body += struct.pack('!B', 0) # reserved
        # HPAI
        self.body += self._pack_hpai()
        return self.body

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body['communication_channel_id'] = self._unpack_stream('!B', message)
            self.body['reserved'] = self._unpack_stream('!B', message)
            # HPAI
            self.body['hpai'] = self._unpack_hpai(message)
        except Exception as e:
            LOGGER.exception(e)


class KnxDisconnectResponse(KnxMessage):

    def __init__(self, message=None, communication_channel=None,
                 knx_source=None, knx_destination=None):
        super(KnxDisconnectResponse, self).__init__()
        if message:
            self.unpack_knx_message(message)
        else:
            self.header['service_type'] = 0x020a
            self.header['total_length'] = 8
            self.communication_channel = communication_channel
            self.pack_knx_message()

    def _pack_knx_body(self):
        # discovery endpoint
        self.body = struct.pack('!B', self.communication_channel)  # channel id
        self.body += struct.pack('!B', 0)  # status
        return self.body

    def _unpack_knx_body(self, message):
        try:
            message = io.BytesIO(message)
            self.body['communication_channel_id'] = self._unpack_stream('!B', message)
            self.body['status'] = self._unpack_stream('!B', message)
        except Exception as e:
            LOGGER.exception(e)

# TODO: implement routing requests (multicast?)
#       ROUTING_INDICATION
#       ROUTING_LOST_MESSAGE

# TODO: implement device configuration requests
#       DEVICE_CONFIGURATION_REQUEST
#       DEVICE_CONFIGURATION_ACK