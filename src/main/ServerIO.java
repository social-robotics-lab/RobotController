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
		if (size == 0) throw new IOException();
		return readData(size);
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
