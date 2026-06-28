package com.example;

import java.io.File;
import java.io.FileReader;

public class App {
    public static void main(String[] args) {
        App app = new App();
        System.out.println(app.greet("World"));
    }

    String greet(String name) {
        return "Hello, " + name + "!";
    }

    String readFile(String path) throws Exception {
        File file = new File(path);
        FileReader reader = new FileReader(file);
        char[] buffer = new char[1024];
        reader.read(buffer);
        reader.close();
        return new String(buffer);
    }
}
