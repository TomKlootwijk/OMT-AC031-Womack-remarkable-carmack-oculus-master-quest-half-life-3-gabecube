package org.atomos.radio;

import android.test.InstrumentationTestCase;
import org.json.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.Base64;

/** Synthetic wire fixtures; no physical captures and no network calls. */
public final class DecoderTest extends InstrumentationTestCase {
    private JSONObject inspect(byte[] bytes)throws Exception {
        File file=File.createTempFile("synthetic-decoder-",".pcap",getInstrumentation().getTargetContext().getCacheDir());
        try {Files.write(file.toPath(),bytes);return new JSONObject(PacketDecoder.decode(file));}
        finally {Files.deleteIfExists(file.toPath());}
    }
    private static byte[] fixture(String base64){return Base64.getDecoder().decode(base64);}
    private static byte[] firstIp(){byte[] raw=fixture(RAW);return Arrays.copyOfRange(raw,40,raw.length);}
    private static byte[] capture(byte[] packet,int link,boolean little,boolean nano,int fraction,int repeats)throws Exception {
        ByteArrayOutputStream out=new ByteArrayOutputStream();ByteOrder order=little?ByteOrder.LITTLE_ENDIAN:ByteOrder.BIG_ENDIAN;
        ByteBuffer h=ByteBuffer.allocate(24).order(order);h.putInt(nano?0xa1b23c4d:0xa1b2c3d4).putShort((short)2).putShort((short)4).putInt(0).putInt(0).putInt(65535).putInt(link);out.write(h.array());
        for(int i=0;i<repeats;i++){ByteBuffer r=ByteBuffer.allocate(16).order(order);r.putInt(1700000000).putInt(fraction).putInt(packet.length).putInt(packet.length);out.write(r.array());out.write(packet);}return out.toByteArray();
    }
    public void testWifiSsidRatesAndRsn()throws Exception {
        JSONObject ssid=new JSONObject(WifiIeDecoder.decode(0,0,new byte[]{'t','e','s','t'}));assertEquals("test",ssid.getJSONObject("fields").getString("ssid_utf8"));
        JSONObject invalidUtf8=new JSONObject(WifiIeDecoder.decode(0,0,new byte[]{(byte)255}));assertTrue(invalidUtf8.getJSONObject("fields").isNull("ssid_utf8"));
        JSONObject rate=new JSONObject(WifiIeDecoder.decode(1,0,new byte[]{(byte)0x82,12}));assertEquals(2,rate.getJSONObject("fields").getJSONArray("rates").getJSONObject(0).getInt("rate_500_kbps"));assertTrue(rate.getJSONObject("fields").getJSONArray("rates").getJSONObject(0).getBoolean("basic"));
        byte[] rsn={1,0,0,15,(byte)172,4,1,0,0,15,(byte)172,4,1,0,0,15,(byte)172,2,(byte)192,0};
        JSONObject r=new JSONObject(WifiIeDecoder.decode(48,0,rsn));assertEquals("decoded",r.getString("status"));assertEquals("CCMP-128",r.getJSONObject("fields").getJSONObject("group_cipher").getString("label"));assertEquals("PSK",r.getJSONObject("fields").getJSONArray("akm_suites").getJSONObject(0).getString("label"));assertTrue(r.getJSONObject("fields").getBoolean("management_frame_protection_capable"));
    }
    public void testWifiMalformedUnknownAndLabels()throws Exception {
        assertEquals("malformed",new JSONObject(WifiIeDecoder.decode(48,0,new byte[]{1,0,0})).getString("status"));
        assertEquals("malformed",new JSONObject(WifiIeDecoder.decode(3,0,new byte[2])).getString("status"));
        assertEquals("unsupported",new JSONObject(WifiIeDecoder.decode(199,0,new byte[0])).getString("status"));
        assertEquals("EHT capabilities",new JSONObject(WifiIeDecoder.decode(255,108,new byte[]{1,2})).getString("label"));
        JSONObject vendor=new JSONObject(WifiIeDecoder.decode(221,0,new byte[]{0x12,0x34,0x56,7}));assertEquals("12:34:56",vendor.getJSONObject("fields").getString("oui"));assertEquals("not resolved from OUI",vendor.getJSONObject("fields").getString("vendor_identity"));
    }
    public void testClassicEndianAndTimestampUnits()throws Exception {
        for(boolean little:new boolean[]{false,true})for(boolean nano:new boolean[]{false,true}){
            JSONObject report=inspect(capture(firstIp(),101,little,nano,nano?250000000:250000,1));assertEquals("ok",report.getString("status"));JSONObject p=report.getJSONArray("packets").getJSONObject(0);
            assertEquals("1700000000250000000",p.getJSONObject("timestamp").getString("nanoseconds_exact"));assertEquals("DNS",p.getString("protocol"));assertEquals("example.test",p.getJSONObject("dns").getJSONArray("questions").getJSONObject(0).getString("name"));
        }
    }
    public void testVlanAndUnsupportedLink()throws Exception {
        byte[] ip=firstIp(),frame=new byte[18+ip.length];frame[12]=(byte)0x81;frame[13]=0;frame[14]=0;frame[15]=42;frame[16]=8;frame[17]=0;System.arraycopy(ip,0,frame,18,ip.length);
        JSONObject p=inspect(capture(frame,1,true,false,0,1)).getJSONArray("packets").getJSONObject(0);assertEquals(42,p.getJSONArray("vlans").getJSONObject(0).getInt("vid"));assertEquals("DNS",p.getString("protocol"));
        JSONObject unsupported=inspect(capture(ip,9999,true,false,0,1));assertEquals(1,unsupported.getInt("unsupported_packets"));assertTrue(unsupported.getBoolean("complete"));assertEquals("partial",unsupported.getString("status"));
    }
    public void testMixedPcapngSectionsInterfacesAndBinaryTime()throws Exception {
        JSONObject r=inspect(fixture(MIXED));assertEquals("ok",r.getString("status"));assertEquals(2,r.getInt("sections"));assertEquals(3,r.getInt("packets_seen"));
        String[] expected={"1700000000250000000","1700000000500000000","1700000000750000000"};for(int i=0;i<3;i++)assertEquals(expected[i],r.getJSONArray("packets").getJSONObject(i).getJSONObject("timestamp").getString("nanoseconds_exact"));
        assertEquals("1024",r.getJSONArray("interfaces").getJSONObject(1).getString("timestamp_denominator"));assertEquals("7",r.getJSONArray("interfaces").getJSONObject(1).getString("timestamp_offset_seconds"));
        JSONObject bad=inspect(fixture(UNKNOWN_IF));assertFalse(bad.getBoolean("complete"));assertEquals("malformed",bad.getString("status"));assertTrue(bad.getJSONArray("issues").getString(0).contains("unknown interface"));
    }
    public void testDnsPointerLoopAndCaptureTruncation()throws Exception {
        JSONObject loop=inspect(fixture(LOOP));assertEquals(1,loop.getInt("malformed_packets"));assertTrue(loop.getJSONArray("issues").getString(0).contains("pointer loop"));
        byte[] capture=capture(firstIp(),101,true,false,0,1);JSONObject cut=inspect(Arrays.copyOf(capture,capture.length-1));assertFalse(cut.getBoolean("complete"));assertEquals("malformed",cut.getString("status"));
        capture[32]=(byte)255;capture[33]=(byte)255;capture[34]=(byte)255;capture[35]=(byte)255;assertFalse(inspect(capture).getBoolean("complete"));
    }
    public void testPcapngPreservesSubnanosecondRationalTimestamp()throws Exception {
        byte[] b=fixture(MIXED);
        // Fixture's big-endian section EPB starts at 292. Advance its low timestamp
        // word from an exact half second by one 1/1024-second tick.
        b[311]++;
        JSONObject t=inspect(b).getJSONArray("packets").getJSONObject(1).getJSONObject("timestamp");
        assertEquals("1740800000513",t.getString("seconds_numerator"));
        assertEquals("1024",t.getString("seconds_denominator"));assertTrue(t.isNull("nanoseconds_exact"));
    }
    public void testHttpTlsFragmentAndTruncatedFrameEvidence()throws Exception {
        JSONObject r=inspect(fixture(ETHERNET));assertTrue(r.getBoolean("complete"));assertEquals("partial",r.getString("status"));assertEquals(17,r.getInt("packets_seen"));assertEquals(2,r.getJSONObject("protocol_counts").getInt("HTTP"));assertEquals(2,r.getJSONObject("protocol_counts").getInt("TLS"));assertEquals(3,r.getJSONObject("protocol_counts").getInt("DNS"));
        JSONArray packets=r.getJSONArray("packets");assertEquals("GET",packets.getJSONObject(5).getJSONObject("http").getString("method"));assertTrue(packets.getJSONObject(5).getJSONObject("http").getBoolean("request_target_omitted"));assertEquals(200,packets.getJSONObject(6).getJSONObject("http").getInt("status_code"));
        assertEquals(1,packets.getJSONObject(10).getJSONObject("tls").getInt("handshake_type"));assertTrue(packets.getJSONObject(11).getBoolean("payload_opaque"));assertTrue(packets.getJSONObject(11).isNull("encrypted"));assertFalse(r.getJSONObject("semantics").getBoolean("decryption"));assertTrue(packets.getJSONObject(13).getBoolean("transport_payload_incomplete"));assertEquals("IPv4 fragment",packets.getJSONObject(14).getString("protocol"));assertEquals(1,r.getInt("capture_truncated_packets"));assertEquals(1,r.getInt("malformed_packets"));
    }
    public void testBoundedPacketDetailsAndWifiBody()throws Exception {
        JSONObject r=inspect(capture(firstIp(),101,true,false,0,201));assertEquals(201,r.getInt("packets_seen"));assertEquals(200,r.getJSONArray("packets").length());assertEquals(1,r.getInt("packet_details_omitted"));assertEquals("malformed",new JSONObject(WifiIeDecoder.decode(0,0,new byte[4097])).getString("status"));
    }
    private static byte[] udpIp(byte[] payload,int src,int dst,int declaredLength){
        byte[] b=new byte[28+payload.length];ByteBuffer v=ByteBuffer.wrap(b).order(ByteOrder.BIG_ENDIAN);b[0]=0x45;v.putShort(2,(short)b.length);b[8]=64;b[9]=17;b[12]=(byte)192;b[13]=0;b[14]=2;b[15]=10;b[16]=(byte)192;b[17]=0;b[18]=2;b[19]=20;
        v.putShort(20,(short)src).putShort(22,(short)dst).putShort(24,(short)declaredLength).putShort(26,(short)0x1234);System.arraycopy(payload,0,b,28,payload.length);return b;
    }
    private JSONObject inspectUdp(byte[] payload,int src,int dst,int declaredLength)throws Exception{return inspect(capture(udpIp(payload,src,dst,declaredLength),101,true,false,0,1)).getJSONArray("packets").getJSONObject(0);}
    public void testUdpRawPreviewEscapesBoundAndIncomplete()throws Exception {
        byte[] bytes={'H','i',10,0,(byte)255,'\\',9};JSONObject p=inspectUdp(bytes,4000,4001,15);
        assertEquals("Hi\\n\\x00\\xff\\\\\\t",p.getString("udp_payload_text"));assertEquals("48690a00ff5c09",p.getString("udp_payload_hex"));assertEquals(7,p.getInt("udp_payload_declared_bytes"));assertEquals(7,p.getInt("udp_payload_captured_bytes"));assertTrue(p.getBoolean("udp_payload_complete"));assertEquals("1234",p.getString("udp_checksum_hex"));assertFalse(p.getBoolean("udp_checksum_verified"));
        byte[] large=new byte[200];Arrays.fill(large,(byte)'A');JSONObject bound=inspectUdp(large,4000,4001,208);assertEquals(128,bound.getInt("udp_payload_preview_bytes"));assertEquals(256,bound.getString("udp_payload_hex").length());assertTrue(bound.getBoolean("udp_payload_preview_truncated"));assertTrue(bound.getBoolean("udp_payload_complete"));
        JSONObject shortPayload=inspectUdp(bytes,4000,4001,108);assertEquals(100,shortPayload.getInt("udp_payload_declared_bytes"));assertEquals(7,shortPayload.getInt("udp_payload_captured_bytes"));assertFalse(shortPayload.getBoolean("udp_payload_complete"));assertFalse(shortPayload.getBoolean("udp_payload_preview_truncated"));assertTrue(shortPayload.getBoolean("transport_payload_incomplete"));
        JSONObject fragment=inspect(fixture(ETHERNET)).getJSONArray("packets").getJSONObject(13);assertEquals("SYNTHETI",fragment.getString("udp_payload_text"));assertFalse(fragment.getBoolean("udp_payload_complete"));assertFalse(fragment.has("udp_application"));
    }
    public void testUdpNtpWireFieldsRemainExactAndCandidate()throws Exception {
        byte[] b=new byte[48];ByteBuffer v=ByteBuffer.wrap(b).order(ByteOrder.BIG_ENDIAN);b[0]=0x24;b[1]=2;b[2]=6;b[3]=-20;v.putInt(4,-32768);v.putInt(8,65536);v.putInt(40,-1);v.putInt(44,0x80000001);
        JSONObject p=inspectUdp(b,123,40000,56),ntp=p.getJSONObject("udp_application");assertEquals("UDP",p.getString("protocol"));assertEquals("NTP",ntp.getString("protocol"));assertEquals(4,ntp.getInt("mode"));assertEquals(-20,ntp.getInt("precision_exponent"));assertEquals("-32768",ntp.getJSONObject("root_delay_seconds").getString("numerator"));assertFalse(ntp.getBoolean("authentication_verified"));
        JSONObject time=ntp.getJSONObject("transmit_timestamp");assertEquals("4294967295",time.getString("seconds_field"));assertEquals("2147483649",time.getString("fraction_field"));assertEquals("4294967296",time.getString("fraction_denominator"));assertTrue(time.isNull("era"));
        assertFalse(inspectUdp(new byte[4],123,40000,12).has("udp_application"));assertFalse(inspectUdp(b,40000,40001,56).has("udp_application"));b[0]=0x26;assertFalse(inspectUdp(b,123,40000,56).has("udp_application"));
    }
    public void testUdpDhcpCookieOptionsAndMalformedEvidence()throws Exception {
        byte[] b=new byte[244];b[0]=1;b[1]=1;b[2]=6;b[236]=99;b[237]=(byte)130;b[238]=83;b[239]=99;b[240]=53;b[241]=1;b[242]=1;b[243]=(byte)255;
        JSONObject d=inspectUdp(b,68,67,252).getJSONObject("udp_application");assertEquals("DHCP",d.getString("protocol"));assertEquals("Discover",d.getString("message_type_label"));assertTrue(d.getBoolean("options_end_found"));assertEquals("bounded options parsed",d.getString("options_status"));
        b[241]=10;JSONObject invalid=inspectUdp(b,68,67,252).getJSONObject("udp_application");assertEquals("option value truncated",invalid.getString("options_status"));assertFalse(invalid.getBoolean("options_end_found"));assertFalse(invalid.has("message_type_label"));b[236]=0;assertFalse(inspectUdp(b,68,67,252).has("udp_application"));
    }
    // Embedded copies of the public deterministic synthetic fixtures in examples/packets.
    private static final String RAW="obI8TQACAAQAAAAAAAAAAAAEAAAAAABlZVPxAAdbzRUAAAA6AAAAOkUAADoAAQAAQBH2csAAAgrAAAI1zwgANQAmWoQZGQEAAAEAAAAAAAAHZXhhbXBsZQR0ZXN0AAABAAE=";
    private static final String MIXED="Cg0NChwAAABNPCsaAQAAAP//////////HAAAAAEAAAAsAAAAAQAAAAAABAAJAAEABgAAAA4ACAAAAAAAAAAAAAAAAAAsAAAABgAAAGgAAAAAAAAAJAoGAJAQIhhIAAAASAAAAAIZAAAAAgIZAAAAAQgARQAAOgABAABAEfZywAACCsAAAjXPCAA1ACZahBkZAQAAAQAAAAAAAAdleGFtcGxlBHRlc3QAAAEAAWgAAAAKDQ0KAAAAHBorPE0AAQAA//////////8AAAAcAAAAAQAAACwAZQAAAAQAAAAJAAGKAAAAAA4ACAAAAAAAAAAHAAAAAAAAACwAAAABAAAALAEUAAAABAAAAAkAAQkAAAAADgAIAAAAAAAAAAAAAAAAAAAALAAAAAYAAABcAAAAAAAAAZVPw+YAAAAAOgAAADpFAAA6AAEAAEAR9nLAAAIKwAACNc8IADUAJlqEGRkBAAABAAAAAAAAB2V4YW1wbGUEdGVzdAAAAQABAAAAAABcAAAABgAAAHAAAAABF5ec/mLeF4AAAABOAAAATggAAAAAAAABAAEABgIZAAAAAQAARQAAOgABAABAEfZywAACCsAAAjXPCAA1ACZahBkZAQAAAQAAAAAAAAdleGFtcGxlBHRlc3QAAAEAAQAAAAAAcA==";
    private static final String UNKNOWN_IF="Cg0NChwAAABNPCsaAQAAAP//////////HAAAAAEAAAAsAAAAAQAAAAAABAAJAAEABgAAAA4ACAAAAAAAAAAAAAAAAAAsAAAABgAAAGgAAAAFAAAAJAoGAABAHhhIAAAASAAAAAIZAAAAAgIZAAAAAQgARQAAOgABAABAEfZywAACCsAAAjXPCAA1ACZahBkZAQAAAQAAAAAAAAdleGFtcGxlBHRlc3QAAAEAAWgAAAA=";
    private static final String LOOP="1MOyoQIABAAAAAAAAAAAAAAABAABAAAAAPFTZaCGAQA8AAAAPAAAAAIZAAAAAgIZAAAAAQgARQAALgABAABAEfZ+wAACNcAAAgoANc8IABpKjCAggYAAAQAAAAAAAMAMAAEAAQ==";
    private static final String ETHERNET="1MOyoQIABAAAAAAAAAAAAAAABAABAAAAAPFTZaCGAQBIAAAASAAAAAIZAAAAAgIZAAAAAQgARQAAOgABAABAEfZywAACCsAAAjXPCAA1ACZahBkZAQAAAQAAAAAAAAdleGFtcGxlBHRlc3QAAAEAAQHxU2WIigEAWAAAAFgAAAACGQAAAAICGQAAAAEIAEUAAEoAAQAAQBH2YsAAAjXAAAIKADXPCAA23YsZGYGAAAEAAQAAAAAHZXhhbXBsZQR0ZXN0AAABAAHADAABAAEAAAA8AATLAHEHAvFTZXCOAQA2AAAANgAAAAIZAAAAAgIZAAAAAQgARQAAKAABAABABo59wAACCsYzZBScQABQAAAD6AAAAABQAv//IxgAAAPxU2VYkgEANgAAADYAAAACGQAAAAICGQAAAAEIAEUAACgAAQAAQAaOfcYzZBTAAAIKAFCcQAAAB9AAAAPpUBL//xs3AAAE8VNlQJYBADYAAAA2AAAAAhkAAAACAhkAAAABCABFAAAoAAEAAEAGjn3AAAIKxjNkFJxAAFAAAAPpAAAH0VAQ//8bOAAABfFTZSiaAQB4AAAAeAAAAAIZAAAAAgIZAAAAAQgARQAAagABAABABo47wAACCsYzZBScQABQAAAD6QAAB9FQGP//xlYAAEdFVCAvc3ludGhldGljIEhUVFAvMS4xDQpIb3N0OiBleGFtcGxlLnRlc3QNCkNvbm5lY3Rpb246IGNsb3NlDQoNCgbxU2UQngEAgQAAAIEAAAACGQAAAAICGQAAAAEIAEUAAHMAAQAAQAaOMsYzZBTAAAIKAFCcQAAAB9EAAAQrUBj//9fxAABIVFRQLzEuMSAyMDAgT0sNCkNvbnRlbnQtVHlwZTogdGV4dC9wbGFpbg0KQ29udGVudC1MZW5ndGg6IDEwDQoNCnN5bnRoZXRpYwoH8VNl+KEBADYAAAA2AAAAAhkAAAACAhkAAAABCABFAAAoAAEAAEAGjn3AAAIKxjNkFJxBAbsAAAPoAAAAAFAC//8hrAAACPFTZeClAQA2AAAANgAAAAIZAAAAAgIZAAAAAQgARQAAKAABAABABo59xjNkFMAAAgoBu5xBAAAH0AAAA+lQEv//GcsAAAnxU2XIqQEANgAAADYAAAACGQAAAAICGQAAAAEIAEUAACgAAQAAQAaOfcAAAgrGM2QUnEEBuwAAA+kAAAfRUBD//xnMAAAK8VNlsK0BAH8AAAB/AAAAAhkAAAACAhkAAAABCABFAABxAAEAAEAGjjTAAAIKxjNkFJxBAbsAAAPpAAAH0VAY//9SlwAAFgMBAEQBAABAAwMAAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHwAAAsAvAQAAFQAAABEADwAADGV4YW1wbGUudGVzdAvxU2WYsQEASwAAAEsAAAACGQAAAAICGQAAAAEIAEUAAD0AAQAAQAaOaMYzZBTAAAIKAbucQQAAB9EAAAQyUBj//68qAAAXAwMAEAABAgMEBQYHCAkKCwwNDg8M8VNlgLUBAFwAAABcAAAAAhkAAAACAhkAAAABht1gAAAAACYRQCABDbgACgAAAAAAAAAAABAgAQ24AAsAAAAAAAAAAABTzwkANQAmgr4ZGQEAAAEAAAAAAAAHZXhhbXBsZQR0ZXN0AAAcAAEN8VNlaLkBADIAAAAyAAAAAhkAAAACAhkAAAABCABFAAAkAwkgAEARa27AAAIKxjNkFL9ov2kAM8LGU1lOVEhFVEkO8VNlUL0BAEUAAABFAAAAAhkAAAACAhkAAAABCABFAAA3AwkAAkARi1nAAAIKxjNkFEMtRlJBR01FTlQtAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/FTZTjBAQAfAAAAHwAAAAIZAAAAAgIZAAAAAYi1U1lOVEhFVElDIFVOS05PV04Q8VNlIMUBABgAAAA4AAAAAhkAAAACAhkAAAABCABFAAAqAAEAAEAR";
}
