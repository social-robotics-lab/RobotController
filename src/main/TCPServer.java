package main;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.json.JSONObject;

import servo.ServoConverter;
import utils.AxisReader;
import utils.IdleMotionPlayer;
import utils.MotionPlayer;
import utils.PosePlayer;
import utils.SpeechPlayer;

public class TCPServer implements Runnable {

	private final int port;

	public TCPServer (int port) {
		this.port = port;
	}

	@Override
	public void run() {
		try (ServerSocket serverSocket = new ServerSocket(port)){
			ExecutorService ex = Executors.newCachedThreadPool();
			while (true) {
				Socket socket = serverSocket.accept();
				ex.execute(new RecvThread(socket));
			}
		} catch (IOException e) {
			e.printStackTrace();
		}
	}

	private class RecvThread implements Runnable {
		private Socket socket;

		public RecvThread(Socket socket) {
			this.socket = socket;
		}

		@Override
		public void run() {
			try (InputStream is = socket.getInputStream();
				OutputStream os = socket.getOutputStream()) {
				ServerIO io = new ServerIO(is, os);
				byte[] cmd_bytes = io.read();
				String cmd = new String(cmd_bytes);
				if (cmd.equals("play_wav")) {
					byte[] wav_bytes = io.read();
					SpeechPlayer.play(wav_bytes);
				} else if (cmd.equals("stop_wav")) {
					SpeechPlayer.stop();
				} else if (cmd.equals("play_pose")) {
					byte[] pose_bytes = io.read();
					PosePlayer.play(pose_bytes);
				} else if (cmd.equals("stop_pose")) {
					PosePlayer.stop();
				} else if (cmd.equals("play_motion")) {
					byte[] motion_bytes = io.read();
					MotionPlayer.play(motion_bytes);
				} else if (cmd.equals("stop_motion")) {
					MotionPlayer.stop();
				} else if (cmd.equals("play_idle_motion")) {
					byte[] idle_bytes = io.read();
					IdleMotionPlayer.play(idle_bytes);
				} else if (cmd.equals("stop_idle_motion")) {
					IdleMotionPlayer.stop();
				} else if (cmd.equals("read_axes")) {
					Map<Byte, Short> map = AxisReader.read();
					JSONObject obj = ServoConverter.mapToJson(map);
					String text = obj.toString();
					io.write(text.getBytes());
				}
			} catch (IOException e) {
				e.printStackTrace();
			} finally {
				try {
					socket.close();
				} catch (IOException e) {}
			}
		}
	}
}
