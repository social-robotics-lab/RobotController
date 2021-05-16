package main;
import java.io.IOException;
import java.util.Map;

import org.json.JSONException;
import org.json.JSONObject;

import servo.ServoConverter;
import utils.AxisReader;


public class ReadServer extends TCPServer {

	public ReadServer (int port) {
		super(port);
	}

	@Override
	void doTask(ServerIO io) {
		try {
			Map<Byte, Short> map = AxisReader.read();
			JSONObject obj = ServoConverter.mapToJson(map);
			String text = obj.toString();
			io.write(text.getBytes());
		} catch (JSONException | IOException e) {
			e.printStackTrace();
		}

	}
}
