/* forward_api_calls.c: forward XMLRPC calls to the Node Manager
 * Used as a shell, this code works in tandem with sshd
 * to allow authenticated remote access to a localhost-only service.
 *
 * Bugs:
 * Doesn't handle Unicode properly.  UTF-8 is probably OK.
 *
 * Change History:
 * 2006/09/14: [deisenst] Switched to PF_UNIX sockets so that SO_PEERCRED works
 * 2006/09/08: [deisenst] First version.
 */

static const int TIMEOUT_SECS = 30;
const char *API_addr = "/tmp/node_mgr_api";

static const char *Header =
  "POST / HTTP/1.0\r\n"
  "Content-Type: text/xml\r\n"
  "Content-Length: %d\r\n"
  "\r\n%n";

static const char *Error_template =
  "<?xml version='1.0'?>\n"
  "<methodResponse>\n"
  "<fault>\n"
  "<value><struct>\n"
  "<member>\n"
  "<name>faultCode</name>\n"
  "<value><int>1</int></value>\n"
  "</member>\n"
  "<member>\n"
  "<name>faultString</name>\n"
  "<value><string>%s: %s</string></value>\n"
  "</member>\n"
  "</struct></value>\n"
  "</fault>\n"
  "</methodResponse>\n";

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>

static void ERROR(const char *s) {
  printf(Error_template, s, strerror(errno));
  exit(1);
}

int main(int argc, char **argv, char **envp) {
  ssize_t len;
  char header_buf[4096];
  char content_buf[4096];
  size_t content_len;
  int sockfd;
  struct sockaddr_un addr;
  int consecutive_newlines;

  alarm(TIMEOUT_SECS);

  /* read xmlrpc request from stdin
   * 4 KiB ought to be enough for anyone
   */
  content_len = 0;
  while(content_len < sizeof content_buf) {
    len = read(0,
	       content_buf + content_len,
	       sizeof content_buf - content_len);
    if(len < 0) ERROR("read()");
    else if(0 == len) break;
    content_len += len;
  }

  /* connect to the API server */
  sockfd = socket(PF_UNIX, SOCK_STREAM, 0);
  if(sockfd < 0)
    ERROR("socket()");
  memset(&addr, 0, sizeof addr);
  addr.sun_family = AF_UNIX;
  strncpy(addr.sun_path, API_addr, sizeof addr.sun_path);
  if(connect(sockfd, (struct sockaddr *)&addr, sizeof addr) < 0)
    ERROR("connect()");

  /* send the request */
  snprintf(header_buf, sizeof header_buf, Header, content_len, &len);
  write(sockfd, header_buf, len);
  write(sockfd, content_buf, content_len);
  shutdown(sockfd, SHUT_WR);

  /* forward the response */
  consecutive_newlines = 0;
  while((len = read(sockfd, content_buf, sizeof content_buf)) != 0) {
    size_t processed_len = 0;
    if(len < 0) {
      /* "Connection reset by peer" is not worth bothering the user. */
      if(ECONNRESET == errno) break;
      else ERROR("read()");
    }
    content_len = len;

    while(consecutive_newlines < 2 && processed_len < content_len) {
      char ch = content_buf[processed_len++];
      if(ch == '\n') consecutive_newlines++;
      else if(!isspace(ch)) consecutive_newlines = 0;
    }

    if(processed_len < content_len) {
      len = fwrite(content_buf + processed_len, sizeof (char),
		   content_len - processed_len, stdout);
      /* make sure faults don't mess up previously sent xml */
      if(len < content_len - processed_len) ERROR("fwrite()");
    }
  }

  /* goodbye */
  shutdown(sockfd, SHUT_RD);
  close(sockfd);

  return 0;
}
