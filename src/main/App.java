package main;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;


public class App {

	public static void main(String[] args) {
		ExecutorService service = Executors.newFixedThreadPool(3);
		service.execute(new SpeechServer(Params.speechPort));
		service.execute(new PoseServer(Params.posePort));
		service.execute(new ReadServer(Params.readPort));
	}
}

