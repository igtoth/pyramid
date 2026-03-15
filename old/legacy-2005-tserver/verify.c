#ifndef lint
static char rcsid[] = "$Id: dial.c,v 0.2 2005/08/23 14:55:34 epi Exp $";
/* Author= Ighor Toth <igtoth@gmail.com> - verify.c, v0.2 2005/10/18 10:02:04 */
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "tlibrary.h"
#include "kvlist.h"
#include "convert.h"
#include "connection.h"
                /* Auto Dial parameters:                                     */
char *dest_dn;  /*   the destination DN (where the call should be placed to) */
char *temp_dn;  /*   temporary DN used as origination of outgoing call       */
char *agent_dn; /*   agent DN where call should be transferred after dest_dn */
                /*   answers the call                                        */
int answer_timeout  = 30; /* how long to wait for answer (approx. 5 rings) */
int redial_delay    = 60; /* how long to wait before re-dial (one minute)  */
int redial_attempt  = 10; /* when to gave up (after 10 attempts)           */
int request_timeout =  5; /* timeout for requests sent to TServer          */
int contador=0, continuar=1, hangup=0;
int temp_user_data;
/*-------------------------------------------------------------------------*/
TKVList *user_data;
TConnectionID conn_id;    /* ConnID of the call (set in dispatch_function) */
enum call_status {
	stat_NotInitialized,
	stat_Idle,
	stat_Dialed,
	stat_Answered,
	stat_Released
}
current_status = stat_NotInitialized;
void textcolor(int attr, int fg, int bg);
static void dispatch_function      (TEvent *event);
static void wait_for_status_changed(TServer server, int timeout_secs);
int main (int argc, char **argv){
	char *server_name = NULL;
	TServer server;  char *p; int i, y, rc, port;
	if (argc < 3) {
		printf(" = Genesys CTI \n");
		printf(" = Verify T-Server and PBX \n");
		printf(" = Ighor Toth <igtoth@gmail.com> \n");
		printf(" = verify.c, v0.2 2005/10/18 10:02:04\n");
		
		printf("Usage: %s test_dn -h tserver:port\n", argv[0]);
		printf("\n");
		exit(1);
	}
	temp_dn  = argv[1];
	if (!strcmp(argv[2], "-h")) server_name = argv[3];
	conn_startup();       /* need to initialize socket layer at the beginning */
	atexit(conn_cleanup); /* and cleanup it before exit (mandatory for WinNT) */
	if (server_name && (p = strchr(server_name, ':')) != NULL) {
		*p++ = 0;
		port = atoi(p);
		
		/*
		 * Opening connection to TServer using hostname/port specification:
		 */
	printf("\n<-- Trying to open connection with T-Server.");
		server = TOpenServerEx(server_name, /* hostname of TServer     */
                                  port, /* TServer port            */
                     dispatch_function, /* dispatch function       */
                  "IBM_Dial_Test_Prog", /* application name        */
                                  NULL, /* app password (not used) */
                             SyncMode); /* using synchronous mode  */
  	} 
	if (server < 0) {
		printf("ERROR: Cannot open TServer\n");
		return 1;
		exit(1);
	} else {
		printf("\n*** Opened connection with T-Server successful!");
	}
	wait_for_status_changed(server, request_timeout);
	if (current_status == stat_NotInitialized) {
		printf("ERROR: Unable to register %s after %d sec\n", temp_dn, answer_timeout);
		return 1;
		exit(1);
	} else {
		printf("\n*** DN %s Registered!",temp_dn);
	}
	printf("\n<-- Unregister DN: %s",temp_dn);
	if(TUnregisterAddress(server,temp_dn,RegisterDefault,NULL) < 0){		
		printf("\nERROR: Unable to unregister DN: %s",temp_dn);
		return 1;
		exit(1);
	} else {
		wait_for_status_changed(server, request_timeout);		
		printf("\n*** DN %s unregistered ",temp_dn);
	}
	printf("\n<-- Closing connection to T-Server");
	if(TCloseServer(server) < 0){
		printf("\nERROR: Unable to close connection to T-server: %s",server_name);
		return 1;
		exit(1);
	} else {
		printf("\n*** Closed connection to T-server: %s",server_name);
	}
	printf("\n*** Exit...");
	return 0;
	exit(0);
} /* end_main_function */
/* ------------------------------------------- */
/* 
 * User-defined dispatch function is called by TLibrary whenever an event
 * comes from TServer:
 */
/* ------------------------------------------- */
static void dispatch_function (TEvent *event)
{
	/* printf("\nDISPATCH_FUNCTION CALLED"); */
	textcolor(BRIGHT, RED, BLACK);
	printf("\n--> %s", TGetMessageTypeName(event->Event));
	textcolor(RESET, WHITE, BLACK);	
	switch (event->Event){
		case EventError:
			printf("\nERROR: Cannot perform the request by T-Server");
			exit(1);
			break;
		case EventServerConnected:
			printf("\n*** Successful connection with TServer established");
			break;
  		case EventServerDisconnected:
    			current_status = stat_NotInitialized;
    			break;
		case EventLinkConnected:
			printf("\n<-- Register DN: %s",temp_dn);
			if (TRegisterAddress(event->Server, temp_dn, ModeShare,
			    RegisterDefault, AddressTypeDN, NULL) < 0) {
      				printf("\nERROR: Cannot register DN %d\n", temp_dn);
      				exit(1);
    			}
    			break;
		case EventRegistered:
			current_status = stat_Idle;
			break;
		case EventRinging:
			if(TAnswerCall(event->Server, temp_dn, event->ConnID, NULL, NULL) < 0){
      				printf("\nERROR: Cannot answer call with ConnId %s\n", connid_to_str(event->ConnID));
      				exit(1);
			} else {
				printf("\n*** Call answered! ConnId: %s",connid_to_str(event->ConnID));
			}
			conn_id = event->ConnID;
			current_status = stat_Answered;
			break;
		case EventDialing:
			printf("\n*** ConnID = %s", connid_to_str(event->ConnID));
			printf("\n<-- Ringing! Waiting to be answered...");
			conn_id = event->ConnID;
			break;
		case EventDestinationBusy:	
			TReleaseCall(event->Server, event->ThisDN, event->ConnID, NULL, NULL);
			current_status = stat_Released;
			break;
		case EventReleased:
			current_status = stat_Idle;
			break;
		case EventEstablished:
			if (event->UserData){
				TKVListPrint(stdout, event->UserData, "\n*** UserData:");
				printf("*** TKV List (Userdata) Printed");
			}
			conn_id = event->ConnID;
			current_status = stat_Answered;
			break;
	}
}
/* ------------------------------------------- */
static void wait_for_status_changed(TServer server, int timeout_sec){
	enum call_status old_status = current_status;
	int current_time = time(NULL),
	time_started = current_time,
	time_to_exit = time_started + timeout_sec;
	do {
		if (TScanServer(server, time_to_exit - current_time) < 0) {
			printf("Error in TScanServer\n");
			exit(1);
		}
		if (current_status != old_status) return;
	}
	while ((current_time = time(NULL)) < time_to_exit);
}
/* ------------------------------------------- */
void textcolor(int attr, int fg, int bg){
	char command[13];
	/* Command is the control command to the terminal */
	sprintf(command, "%c[%d;%d;%dm", 0x1B, attr, fg + 30, bg + 40);
	printf("%s", command);
}