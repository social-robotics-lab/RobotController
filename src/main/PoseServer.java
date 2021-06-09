package main;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;

import org.json.JSONObject;

import jp.vstone.RobotLib.CRobotPose;
import led.LedConverter;
import servo.ServoConverter;
import utils.PosePlayer;


public class PoseServer implements Runnable {

	private final int port;
	private final BlockingQueue<String> q;

	public PoseServer (int port) {
		this.port = port;
		this.q = new LinkedBlockingQueue<String>();
	}


	@Override
	public void run() {
		try (ServerSocket serverSocket = new ServerSocket(port)){
			ExecutorService ex = Executors.newCachedThreadPool();
			ex.execute(new PosePlayerThread(q));
			while (true) {
				Socket socket = serverSocket.accept();
				ex.execute(new RecvThread(socket, q));
			}
		} catch (IOException e) {
			e.printStackTrace();
		}
	}

	private class RecvThread implements Runnable {
		private Socket socket;
		private BlockingQueue<String> q;

		public RecvThread(Socket socket, BlockingQueue<String> q) {
			this.socket = socket;
			this.q = q;
		}

		@Override
		public void run() {
			try (InputStream is = socket.getInputStream();
				OutputStream os = socket.getOutputStream()) {
				ServerIO io = new ServerIO(is, os);
				byte[] data = io.read();
				String text = new String(data);
				q.add(text);
			} catch (IOException e) {
				e.printStackTrace();
			} finally {
				try {
					socket.close();
				} catch (IOException e) {}
			}
		}
	}


	// Poseの実行は単一のスレッドで実行しなければ動作しないため、PosePlayerの実行専用のスレッドを作成
	private class PosePlayerThread implements Runnable {
		private BlockingQueue<String> q;

		public PosePlayerThread(BlockingQueue<String> q) {
			this.q = q;
		}

		@Override
		public void run() {
			RobotSys.initialize();
			try {
				while (true) {
					String text = q.take();
					JSONObject obj = new JSONObject(text);
					int msec = obj.getInt("Msec");
					CRobotPose pose = new CRobotPose();
					if (obj.has("ServoMap")) {
						Map<Byte, Short> servoMap = ServoConverter.jsonToMap(obj.getJSONObject("ServoMap"));
						pose.SetPose(servoMap);
					}
					if (obj.has("LedMap")) {
						Map<Byte, Short> ledMap = LedConverter.jsonToMap(obj.getJSONObject("LedMap"));
						pose.SetLed(ledMap);
					}
					PosePlayer.play(msec, pose);
				}
			} catch (InterruptedException e) {
				e.printStackTrace();
			}

		}
	}

}
