#if CONFIG_FREERTOS_UNICORE
#define ARDUINO_RUNNING_CORE 0
#else
#define ARDUINO_RUNNING_CORE 1
#endif

#ifndef LED_BUILTIN
#define LED_BUILTIN 2
#endif

#include "XcpSxIMaster.h"

#define XCP_EVENT_10MS            0 
#define XCP_EVENT_100MS           1

XcpSxIMaster xcpMaster = XcpSxIMaster(115200);
unsigned char amplifier = 10;
double sig = 0.0;

void TaskBlink( void *pvParameters );

// the setup function runs once when you press reset or power the board
void setup() {
  
  // Now set up two tasks to run independently.
  xTaskCreatePinnedToCore(
    TaskBlink
    ,  "TaskBlink"   // A name just for humans
    ,  1024  // This stack size can be checked & adjusted by reading the Stack Highwater
    ,  NULL
    ,  2  // Priority, with 3 (configMAX_PRIORITIES - 1) being the highest, and 0 being the lowest.
    ,  NULL 
    ,  ARDUINO_RUNNING_CORE);

  // Now the task scheduler, which takes over control of scheduling individual tasks, is automatically started.
}

void loop()
{
    xcpMaster.BackgroudTask();
}

/*--------------------------------------------------*/
/*---------------------- Tasks ---------------------*/
/*--------------------------------------------------*/

void TaskBlink(void *pvParameters)  // This is a task.
{
  (void) pvParameters;
  static bool on = true;
  static unsigned char i = 0;

  // initialize digital LED_BUILTIN on pin 13 as an output.
  pinMode(LED_BUILTIN, OUTPUT);

  TickType_t xLastWakeTime = xTaskGetTickCount();
  for (;;) // A Task shall never return or exit.
  {
    vTaskDelayUntil(&xLastWakeTime, 100/portTICK_PERIOD_MS);
    sig = amplifier * sin(i*2*3.14159/20);
    if (++i == 20)
    {
      i = 0;
    }
    xcpMaster.Event(XCP_EVENT_100MS);
    digitalWrite(LED_BUILTIN, on ? HIGH: LOW);  
    on = !on;
  }
}

