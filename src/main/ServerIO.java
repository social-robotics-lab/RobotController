package main;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class ServerIO {

	private final InputStream is;
	private final OutputStream os;

	public ServerIO(InputStream is, OutputStream os) {
		this.is = is;
		this.os = os;
	}

	public byte[] read() throws IOException {
		int size = readSize();
		if (size == 0) return new byte[0];
		return readData(size);
	}

	/**
	 * Reads one bounded frame for audio_stream_v1. A clean EOF before the
	 * header returns null; a truncated, negative, or oversized frame fails
	 * before an unsafe allocation can occur. Legacy read() is unchanged.
	 */
	public byte[] read(int maxBytes) throws IOException {
		if (maxBytes < 0) {
			throw new IllegalArgumentException("Maximum frame size must not be negative.");
		}
		byte[] header = new byte[4];
		int first = is.read();
		if (first < 0) {
			return null;
		}
		header[0] = (byte) first;
		readExact(header, 1, 3, "frame header");
		int size = ByteBuffer.wrap(header).order(ByteOrder.BIG_ENDIAN).getInt();
		if (size < 0) {
			throw new FrameException("Negative frame length: " + size + ".");
		}
		if (size > maxBytes) {
			throw new FrameException(
					"Frame length " + size + " exceeds maximum " + maxBytes + ".");
		}
		if (size == 0) {
			return new byte[0];
		}
		byte[] data = new byte[size];
		readExact(data, 0, size, "frame body");
		return data;
	}

	public void write(byte[] data) throws IOException {
		int size = data.length;
		byte[] buf = ByteBuffer.allocate(4).putInt(size).array();
		os.write(buf, 0, 4);
		os.write(data, 0, size);
		os.flush();
	}

	private int readSize() throws IOException {
		byte[] buf = new byte[4];
		int size = 0;
		while (size < 4) {
			size += is.read(buf, size, 4 - size);
		}
		return ByteBuffer.wrap(buf).order(ByteOrder.BIG_ENDIAN).getInt();
	}

	private byte[] readData(int dataSize) throws IOException {
		byte[] buf = new byte[dataSize];
		int size = 0;
		while (size < dataSize) {
			size += is.read(buf, size, dataSize - size);
		}
		return buf;
	}

	private void readExact(byte[] data, int offset, int length, String part)
			throws IOException {
		int read = 0;
		while (read < length) {
			int count = is.read(data, offset + read, length - read);
			if (count < 0) {
				throw new FrameException("Truncated " + part + ".");
			}
			if (count == 0) {
				int value = is.read();
				if (value < 0) {
					throw new FrameException("Truncated " + part + ".");
				}
				data[offset + read] = (byte) value;
				read++;
			} else {
				read += count;
			}
		}
	}

	static final class FrameException extends IOException {
		private static final long serialVersionUID = 1L;

		private FrameException(String message) {
			super(message);
		}
	}


	public static void main(String[] args) {
		int port = 22222;
		try (ServerSocket serverSocket = new ServerSocket(port)){
			while (true) {
				Socket socket = serverSocket.accept();
				try (InputStream is = socket.getInputStream();
					OutputStream os = socket.getOutputStream()) {
					ServerIO io = new ServerIO(is, os);
					while (true) {
						byte[] data = io.read();
//						System.out.println("data="+new String(data));
						System.out.println("size="+data.length);
						io.write(data);
					}
				} catch (IOException e) {
					//e.printStackTrace();
					System.out.println("[WavServer] Client is disconnected.");
				}
			}
		} catch (IOException e) {
			e.printStackTrace();
		}
	}
}
