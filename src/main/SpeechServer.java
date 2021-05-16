package main;
import java.io.IOException;

import org.json.JSONException;

import utils.SpeechPlayer;


public class SpeechServer extends TCPServer {

	public SpeechServer (int port) {
		super(port);
	}

	@Override
	void doTask(ServerIO io) {
		try {
			byte[] data = io.read();
			SpeechPlayer.play(data);
		} catch (JSONException | IOException e) {
			e.printStackTrace();
		}

	}
}
