#if defined(ESP8266)

#include <pgmspace.h>
#else
#include <avr/pgmspace.h>
#endif

#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <Wire.h> // must be included here so that Arduino library object file references work
#include <OneWire.h>
#include <DallasTemperature.h>

#define DHTTYPE DHT11   // DHT 11
#define RELAYPIN 5
#define ONE_WIRE_BUS D4      // DS18B20 pin
#define SALA 1
#define RELAYPIN1 13
#define RELAYPIN2 4

#if defined(SALA)
	#define ROOMPATH  "home/sala"
#else

#endif
//piagnolo
//const char* ssid = "VodafoneMobileWiFi-27B507";
//const char* password = "3178942140";
//const char* mqtt_server = "192.168.0.151";
//modena
const char* ssid = "Vodafone-A37827721";//"FASTWEB-1-59A637";
const char* password = "EHaCyKqarRq7ahhh";  //"F6324B67CA";
const char* mqtt_server = "192.168.1.9";

const char* room_path = "home/sala";

const int DHTPin = 2;
DHT dht(DHTPin, DHTTYPE);

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature DS18B20(&oneWire);


WiFiClient espClient;
PubSubClient client(espClient);
long lastMsg = 0;
char msg[50];
int value = 0;

long lastMsg_R = 0;
char msg_r[50];
int value_r = 0;
int rele1_status = 0;
int rele2_status = 0;

void setup_wifi() {

	delay(10);
	// We start by connecting to a WiFi network
	Serial.println();
	Serial.print("Connecting to ");
	Serial.println(ssid);

	WiFi.begin(ssid, password);

	while (WiFi.status() != WL_CONNECTED) {
		delay(500);
		Serial.print(".");
	}

	randomSeed(micros());

	Serial.println("");
	Serial.println("WiFi connected");
	Serial.println("IP address: ");
	Serial.println(WiFi.localIP());
}

void callback(char* topic, byte* payload, unsigned int length) {
	Serial.print("Message arrived [");
	Serial.print(topic);
	Serial.print("] ");
	for (int i = 0; i < length; i++) {
		Serial.print((char)payload[i]);
	}
	Serial.println();

	char *relePath = (char*)malloc(100);
	strcpy(relePath, room_path);
	if (strcmp(topic, strcat(relePath, "/stufa")) == 0)
	{

		// Switch on the LED if an 1 was received as first character
		if ((char)payload[0] == '1') {
			Serial.println("Caldaia ON");
			digitalWrite(RELAYPIN1, HIGH);								  // but actually the LED is on; this is because
			rele1_status = 1;															  // it is acive low on the ESP-01)
		}
		else {
			Serial.println("Caldaia OFF");
			digitalWrite(RELAYPIN1, LOW);
			rele1_status = 0;
		}
	}
	free(relePath);
	relePath = (char*)malloc(100);
	strcpy(relePath, room_path);
	if (strcmp(topic, strcat(relePath, "/rele2")) == 0)
	{
		// Switch on the LED if an 1 was received as first character
		if ((char)payload[0] == '1') {
			Serial.println("Rele2 ON");
			digitalWrite(RELAYPIN2, HIGH);								  // but actually the LED is on; this is because
			rele2_status = 1;															  // it is acive low on the ESP-01)
		}
		else {
			Serial.println("Rele2 OFF");
			digitalWrite(RELAYPIN2, LOW);
			rele2_status = 0;
		}
	}
	free(relePath);
}


void reconnect() {
	// Loop until we're reconnected
	while (!client.connected()) {
		Serial.print("Attempting MQTT connection...");
		// Create a random client ID
		String clientId = "ESP8266Client-";
		clientId += String(random(0xffff), HEX);
		// Attempt to connect
		if (client.connect(clientId.c_str())) {
			Serial.println("connected");
			// Once connected, publish an announcement...
			client.publish("home/room1/temperature", "99");
			client.publish("home/room1/rele_status", "0");
			String path = String(room_path) + "/#";
			// ... and resubscribe
			client.subscribe(path.c_str());
		}
		else {
			Serial.print("failed, rc=");
			Serial.print(client.state());
			Serial.println(" try again in 5 seconds");
			// Wait 5 seconds before retrying
			delay(5000);
		}
	}
}

void setup() {
	pinMode(BUILTIN_LED, OUTPUT);     // Initialize the BUILTIN_LED pin as an output
	Serial.begin(115200);
	pinMode(RELAYPIN1, OUTPUT);
	digitalWrite(RELAYPIN1, LOW);
	pinMode(RELAYPIN2, OUTPUT);
	digitalWrite(RELAYPIN2, LOW);
	setup_wifi();
	client.setServer(mqtt_server, 1883);
	client.setCallback(callback);
	delay(10);
	//dht.begin();
	DS18B20.begin();
}

void loop() {

	if (!client.connected()) {
		reconnect();
	}
	client.loop();

	long now = millis();
	if (now - lastMsg > 10000) {
		lastMsg = now;
		float temperature = acquireTemp();
		Serial.print("Publish message: ");
		Serial.println(temperature);
		snprintf(msg, 75, "%s", String(temperature).c_str());
		String temp_path = String(room_path) + "/temperature";
		client.publish(temp_path.c_str(), msg);
		float humidity = dht.readHumidity();
		snprintf(msg, 75, "%s", String(humidity).c_str());
		String hum_path = String(room_path) + "/humidity";
		client.publish(hum_path.c_str(), msg);
	}
}

float acquireTemp() {
	//Serial.println("Requesting DS18B20 temperature...");
	float temp;
	do {
		DS18B20.requestTemperatures();
		temp = DS18B20.getTempCByIndex(0);
		delay(100);
	} while (temp == 85.0 || temp == (-127.0));
	return temp;
}
