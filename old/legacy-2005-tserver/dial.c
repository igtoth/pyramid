#ifndef lint
static char rcsid[] = "$Id: dial.c,v 0.2 2005/08/23 14:55:34 epi Exp $";
/*	Author = Ighor Toth <igtoth@gmail.com> - dial.c, v 0.2 2005/08/23 14:55:34 */
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "tlibrary.h"
#include "kvlist.h"
#include "convert.h"
#include "connection.h"
#define RESET		0
#define BRIGHT 		1
#define DIM		2
#define UNDERLINE 	3
#define BLINK		4
#define REVERSE		7
#define HIDDEN		8
#define BLACK 		0
#define RED		1
#define GREEN		2
#define YELLOW		3
#define BLUE		4
#define MAGENTA		5
#define CYAN		6
#define	WHITE		7
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
	textcolor(BRIGHT, BLUE, BLACK);	
	printf(" = Genesys CTI \n");
	printf(" = Dial_Test_Prog \n");
	printf(" = Ighor Toth <igtoth@gmail.com> \n");
	printf(" = dial.c, v 0.2 2005/08/23 14:55:34 \n");
	textcolor(RESET, WHITE, BLACK);	
	if (argc < 4) {
		printf("Usage: %s orig_dn dest_dn -h tserver:port [options]\n", argv[0]);
		printf("options are:                                                           \n");
		printf("  -t tout_secs      (answer timeout in seconds)                        \n");
		printf("  -d delay_secs     (redial delay in seconds)                          \n");
		printf("  -a number         (redial attempts)                                  \n");
		printf("  -i key_1 value_1  (add integer as user-data)                         \n");
		printf("  -s key_2 value_2  (add string as user-data)                          \n");
		printf("  (You can use how many '-s' '-i' options you want)                    \n");
		printf("  Ex: -s NAME John -s Class First -i Age 21 -s Method In-bound         \n");
		printf("  Default:                                                             \n");	
		printf("  Answer timeout  = 30 (how long to wait for answer (approx. 5 rings)) \n");
		printf("  Redial Delay    = 60 (how long to wait before re-dial (one minute))  \n");
		printf("  Redial Attempt  = 10 (when to gave up (after 10 attempts))           \n");
		textcolor(BRIGHT, RED, BLACK);
		printf("-------------------------------------------------------------------------\n");
		textcolor(RESET, WHITE, BLACK);
		exit(1);
	}
	temp_dn  = argv[1];
	dest_dn  = argv[2];
	if (!strcmp(argv[3], "-h")) server_name = argv[4];
	for (i = 5; i < argc; i++) {
		if (strcmp(argv[i], "-t") == 0){ 
			answer_timeout = atoi(argv[1+i]); 
		} else if (strcmp(argv[i], "-d") == 0){ 
			redial_delay = atoi(argv[1+i]);
		} else if (strcmp(argv[i], "-a") == 0){
			redial_attempt = atoi(argv[1+i]);
		}
	}
	textcolor( BRIGHT, RED, BLACK);
	printf("-------------------------------------------------------------------------");
	textcolor(RESET, WHITE, BLACK);
	printf("\n Using T-Server (host:port): %s",server_name);
	printf("\n Answer timeout = %d",answer_timeout);
	printf("\n Redial Delay   = %d",redial_delay);
	printf("\n Redial Attempt = %d",redial_attempt);
	textcolor( BRIGHT, RED, BLACK);
	printf("\n-------------------------------------------------------------------------");
	textcolor(RESET, WHITE, BLACK);
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
		exit(1);
	} else {
		textcolor(BRIGHT, GREEN, BLACK);
		printf("\n*** Opened connection with T-Server successful!");
		textcolor(RESET, WHITE, BLACK);
	}
	wait_for_status_changed(server, request_timeout);
	if (current_status == stat_NotInitialized) {
		printf("ERROR: Unable to register %s after %d sec\n", temp_dn, answer_timeout);
		exit(1);
	} else {
		textcolor(BRIGHT, GREEN, BLACK);
		printf("\n*** DN %s Registered!",temp_dn);
		textcolor(RESET, WHITE, BLACK);
	}
	TKVList *user_data = TKVListCreate();
	/* TKVListAddString(user_data, "on-behalf-of", agent_dn); */
	printf ("\n<-- Adding User-data to TKV List");
	for (i = 5; i < argc; i++) {
		if (strcmp(argv[i], "-s") == 0){
			TKVListAddString(user_data, argv[1+i], argv[2+i]);
			printf("\n    Added key: %s [String] / value: %s",argv[1+i],argv[2+i]);
		}
		if (strcmp(argv[i], "-i") == 0){
			temp_user_data=atoi(argv[2+i]);
			TKVListAddInt(user_data, argv[1+i], temp_user_data);
			printf("\n    Added key: %s [Integer] / value: %d",argv[1+i],temp_user_data);
		}		
	}
	for (i = 1; i <= redial_attempt; i++) {
		textcolor(BRIGHT, RED, BLACK);
		printf("\n-------------------------------------------------------------------------");
		textcolor(RESET, WHITE, BLACK);
		printf ("\n<-- Dialing %s - Attempt # %d",dest_dn,i);
		rc = TMakeCall(server, /* reference to TServer connection */
                  	temp_dn, /* origination DN                  */
                  	dest_dn, /* destination DN                  */
                     	   NULL, /* location (not used)             */
          	MakeCallRegular, /* call type (regular call)        */
               	      user_data, /* intial UserData for call        */
              	    NULL, NULL); /* reasons/extensions (not used)   */
    		/* TKVListFree(user_data); */
		if (rc < 0) {
			printf("\nERROR: Cannot make a call\n");
			exit(1);
		}
		else current_status = stat_Dialed;
		int c_t = time(NULL), t_s = c_t, t_t_e = t_s + answer_timeout;
		
		y = 1;
		do{
			wait_for_status_changed(server, request_timeout);
			textcolor(BRIGHT, BLUE, BLACK);
			printf("\n    Ringing # %d",y);
			textcolor(RESET, WHITE, BLACK);
			y++;
		}while((current_status == stat_Dialed)&&((c_t = time(NULL)) < t_t_e));
		/* wait_for_status_changed(server, answer_timeout); */
		switch (current_status) {
			case stat_Answered: /* success */
				textcolor(BRIGHT, GREEN, BLACK);
				printf("\n*** Call answered, Success !!!");
				textcolor(RESET, WHITE, BLACK);
				do{
					hangup=1;
					contador++;
					/* printf("%d ",contador); */
					textcolor(BRIGHT, RED, BLACK);
					printf ("\n\n--- Press [ENTER] to Hang-up this call! ---\n");
					textcolor(RESET, WHITE, BLACK);	
					c_t = time(NULL);
					t_s = c_t;
					t_t_e = t_s + answer_timeout;
					hangup=getchar();
					printf("<-- Checking call status ...\n");
					wait_for_status_changed(server, request_timeout);
					if(current_status == stat_Idle){
						printf("\n*** Call was first released by other side...");
					}
 else {
						if (TReleaseCall(server, temp_dn, conn_id, NULL, NULL) < 0) {
							printf("\nERROR: Cannot release the call\n");
							exit(1);
						} else {
							printf("<-- Release call, DN: %s, ConnID: %s",temp_dn,connid_to_str(conn_id));
							current_status = stat_Released;
						}
					}
				}while(current_status == stat_Answered);
				if(current_status == stat_Released){
					printf("\n<-- Wait to release call...");
      					wait_for_status_changed(server, request_timeout);
				}
				/* 
				user_data = TKVListCreate(); 
				TKVListAddInt(user_data, "attempts", i); 
     				 TUpdateUserData(server, 
                     		 	 temp_dn, 
                    			 conn_id, 
                 			 user_data); 
      				TMuteTransfer(server, 
                   			temp_dn, 
                   			conn_id, 
                  			agent_dn, 
   					NULL, NULL, NULL, NULL); 
				*/
				printf("\n<-- Unregister DN: %s",temp_dn);
				if(TUnregisterAddress(server,temp_dn,RegisterDefault,NULL)
 < 0){
					
printf("\nERROR: Unable to unregister DN: %s",temp_dn);
				} else {
					wait_for_status_changed(server, request_timeout);
					textcolor(BRIGHT, GREEN, BLACK);
					
printf("\n*** DN %s unregistered ",temp_dn);
					textcolor(RESET, WHITE, BLACK);
				}
				printf("\n<-- Closing connection to T-Server");
				if(TCloseServer(server) < 0){
	
				printf("\nERROR: Unable to close connection to T-server: %s",server_name);
				} else {
					textcolor(BRIGHT, GREEN, BLACK);
					printf("\n*** Closed connection to T-server: %s",server_name);
					textcolor(RESET, WHITE, BLACK);
				}
				printf("\n*** Exit!\n\n");
				return 0;
    			case stat_Dialed: /* call was not answered: release it and try again */
				printf("\n*** Time-out: Call was not answered!");
      				rc = TReleaseCall(server, /* reference to TServer connection */
                       			temp_dn, /* DN where call is originated     */
                       			conn_id, /* ConnID of the call              */
                   			NULL, NULL); /* reasons/extensions (not used)   */
      				if (rc < 0) {
        				printf("\nERROR: Cannot release the call\n");
        				exit(1);
      				}
      				else current_status = stat_Released;
				/*
				 * Need to wait for call to be release (the same action as if it was released
				 * inside dipatch_function)
				 */
			
			case stat_Released:
				printf("\n*** Wait to release call...");
      				wait_for_status_changed(server, request_timeout);
      				break;
			case stat_NotInitialized:
				printf("ERROR: Lost connection to TServer\n");
				exit(1);
		}  /* end_switch */
		printf("\n!!! Wait %d seconds to redial...",redial_delay);
		textcolor(BRIGHT, RED, BLACK);
		c_t = time(NULL);
		t_s = c_t; 
		t_t_e = t_s + redial_delay;
		hangup=0;
		while((hangup != 10)&&((c_t = time(NULL)) < t_t_e)){
			printf("\n*** If want to stop, press [ENTER] now!\n");
			textcolor(RESET, WHITE, BLACK);
			hangup=getchar();
		}
		if(hangup == 10){
				printf("\n<-- Unregister DN: %s",temp_dn);
				if(TUnregisterAddress(server,temp_dn,RegisterDefault,NULL)
 < 0){
					
printf("\nERROR: Unable to unregister DN: %s",temp_dn);
				} else {
					wait_for_status_changed(server, request_timeout);
					textcolor(BRIGHT, GREEN, BLACK);
					
printf("\n*** DN %s unregistered ",temp_dn);
					textcolor(RESET, WHITE, BLACK);
				}
				printf("\n<-- Closing connection to T-Server");
				if(TCloseServer(server) < 0){
	
				printf("\nERROR: Unable to close connection to T-server: %s",server_name);
				} else {
					textcolor(BRIGHT, GREEN, BLACK);
					printf("\n*** Closed connection to T-server: %s",server_name);
					textcolor(RESET, WHITE, BLACK);
				}
				printf("\n*** Exit!\n\n");
				return 0;
		}
		/* wait_for_status_changed(server, redial_delay); */
	} /* end_redial */
	return 0;
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