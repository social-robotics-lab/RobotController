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
import utils.StreamingAudioPlayer;

public class TCPServer implements Runnable {
	private static final String AUDIO_STREAM_COMMAND = "audio_stream_v1";
	private static final int AUDIO_STREAM_QUEUE_CAPACITY = 25;
	private static final long AUDIO_STREAM_OFFER_TIMEOUT_MS = 20L;
	private static final long AUDIO_STREAM_BARRIER_TIMEOUT_MS = 5000L;
	private static final int AUDIO_STREAM_MAX_RECORD_BYTES = 961;

	private static final int RECORD_START = 0x01;
	private static final int RECORD_DATA = 0x02;
	private static final int RECORD_END = 0x03;
	private static final int RECORD_CANCEL = 0x04;
	private static final int RESPONSE_STATUS = 0x80;
	private static final int RESPONSE_ERROR = 0x81;
	private static final int STATUS_CONNECTION_READY = 0x01;
	private static final int STATUS_STARTED = 0x02;
	private static final int STATUS_ENDED = 0x03;
	private static final int STATUS_CANCELLED = 0x04;
	private static final int ERROR_BUSY = 0x01;
	private static final int ERROR_PROTOCOL = 0x02;
	private static final int ERROR_AUDIO = 0x03;
	private static final int ERROR_QUEUE_OVERFLOW = 0x04;

	private final int port;
	private final StreamingAudioPlayer audioStreamingPlayer;

	public TCPServer (int port) {
		this(port, new StreamingAudioPlayer(
				AUDIO_STREAM_QUEUE_CAPACITY,
				AUDIO_STREAM_OFFER_TIMEOUT_MS,
				AUDIO_STREAM_BARRIER_TIMEOUT_MS));
	}

	TCPServer(int port, StreamingAudioPlayer audioStreamingPlayer) {
		if (audioStreamingPlayer == null) {
			throw new IllegalArgumentException("Audio streaming player must not be null.");
		}
		this.port = port;
		this.audioStreamingPlayer = audioStreamingPlayer;
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

	void handleConnection(Socket connectionSocket)
			throws IOException, InterruptedException {
		try (InputStream is = connectionSocket.getInputStream();
				OutputStream os = connectionSocket.getOutputStream()) {
			ServerIO io = new ServerIO(is, os);
			byte[] cmd_bytes = io.read();
			String cmd = new String(cmd_bytes);
			/* Only audio_stream_v1 keeps the connection open for more records. */
			if (cmd.equals(AUDIO_STREAM_COMMAND)) {
				handleAudioStream(io);
			} else if (cmd.equals("play_wav")) {
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
		}
	}

	private void handleAudioStream(ServerIO io)
			throws IOException, InterruptedException {
		StreamingAudioPlayer.Connection acquired =
				audioStreamingPlayer.tryAcquireConnection();
		if (acquired == null) {
			sendError(io, ERROR_BUSY);
			return;
		}

		try (StreamingAudioPlayer.Connection connection = acquired) {
			sendStatus(io, STATUS_CONNECTION_READY);
			boolean streaming = false;
			while (true) {
				byte[] record;
				try {
					record = io.read(AUDIO_STREAM_MAX_RECORD_BYTES);
				} catch (ServerIO.FrameException exception) {
					throw new ProtocolFailure("Invalid audio stream frame.", exception);
				}
				if (record == null) {
					return;
				}
				if (record.length == 0) {
					throw new ProtocolFailure("Empty audio stream record.");
				}

				int type = record[0] & 0xff;
				if (type == RECORD_START) {
					requireLength(record, 1, "START");
					if (streaming) {
						throw new ProtocolFailure("START received while streaming.");
					}
					startAudio(connection);
					sendStatus(io, STATUS_STARTED);
					streaming = true;
				} else if (type == RECORD_DATA) {
					if (!streaming) {
						throw new ProtocolFailure("DATA received while idle.");
					}
					if (record.length < 3 || ((record.length - 1) & 1) != 0) {
						throw new ProtocolFailure("Invalid DATA PCM length.");
					}
					byte[] pcm = new byte[record.length - 1];
					System.arraycopy(record, 1, pcm, 0, pcm.length);
					StreamingAudioPlayer.OfferResult result =
							offerAudio(connection, pcm);
					if (result == StreamingAudioPlayer.OfferResult.FULL) {
						sendError(io, ERROR_QUEUE_OVERFLOW);
						streaming = false;
					}
				} else if (type == RECORD_END) {
					requireLength(record, 1, "END");
					if (!streaming) {
						throw new ProtocolFailure("END received while idle.");
					}
					endAudio(connection);
					sendStatus(io, STATUS_ENDED);
					streaming = false;
				} else if (type == RECORD_CANCEL) {
					requireLength(record, 1, "CANCEL");
					if (!streaming) {
						throw new ProtocolFailure("CANCEL received while idle.");
					}
					cancelAudio(connection);
					sendStatus(io, STATUS_CANCELLED);
					streaming = false;
				} else {
					throw new ProtocolFailure("Unknown audio stream record type.");
				}
			}
		} catch (ProtocolFailure exception) {
			sendErrorPreserving(io, ERROR_PROTOCOL, exception);
			throw exception;
		} catch (AudioFailure exception) {
			sendErrorPreserving(io, ERROR_AUDIO, exception);
			throw exception;
		}
	}

	private static void requireLength(byte[] record, int expected, String name)
			throws ProtocolFailure {
		if (record.length != expected) {
			throw new ProtocolFailure(name + " record has invalid length.");
		}
	}

	private static void startAudio(StreamingAudioPlayer.Connection connection)
			throws AudioFailure, InterruptedException {
		try {
			connection.start();
		} catch (IOException exception) {
			throw new AudioFailure("Unable to start streaming audio.", exception);
		}
	}

	private static StreamingAudioPlayer.OfferResult offerAudio(
			StreamingAudioPlayer.Connection connection, byte[] pcm)
			throws AudioFailure, InterruptedException {
		try {
			return connection.offerPcm(pcm);
		} catch (IOException exception) {
			throw new AudioFailure("Unable to queue streaming audio.", exception);
		}
	}

	private static void endAudio(StreamingAudioPlayer.Connection connection)
			throws AudioFailure, InterruptedException {
		try {
			connection.end();
		} catch (IOException exception) {
			throw new AudioFailure("Unable to end streaming audio.", exception);
		}
	}

	private static void cancelAudio(StreamingAudioPlayer.Connection connection)
			throws AudioFailure, InterruptedException {
		try {
			connection.cancel();
		} catch (IOException exception) {
			throw new AudioFailure("Unable to cancel streaming audio.", exception);
		}
	}

	private static void sendStatus(ServerIO io, int code) throws IOException {
		sendResponse(io, RESPONSE_STATUS, code);
	}

	private static void sendError(ServerIO io, int code) throws IOException {
		sendResponse(io, RESPONSE_ERROR, code);
	}

	private static void sendResponse(ServerIO io, int type, int code)
			throws IOException {
		io.write(new byte[] { (byte) type, (byte) code });
	}

	private static void sendErrorPreserving(
			ServerIO io, int code, IOException primary) {
		try {
			sendError(io, code);
		} catch (IOException responseFailure) {
			primary.addSuppressed(responseFailure);
		}
	}

	private static final class ProtocolFailure extends IOException {
		private static final long serialVersionUID = 1L;

		private ProtocolFailure(String message) {
			super(message);
		}

		private ProtocolFailure(String message, Throwable cause) {
			super(message, cause);
		}
	}

	private static final class AudioFailure extends IOException {
		private static final long serialVersionUID = 1L;

		private AudioFailure(String message, Throwable cause) {
			super(message, cause);
		}
	}

	private class RecvThread implements Runnable {
		private Socket socket;

		public RecvThread(Socket socket) {
			this.socket = socket;
		}

		@Override
		public void run() {
			try {
				handleConnection(socket);
			} catch (IOException e) {
				e.printStackTrace();
			} catch (InterruptedException e) {
				Thread.currentThread().interrupt();
			} finally {
				try {
					socket.close();
				} catch (IOException e) {}
			}
		}
	}
}
