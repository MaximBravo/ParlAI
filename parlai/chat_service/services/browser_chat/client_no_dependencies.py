#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import json
import websocket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


SHARED = {}
STYLE_SHEET = "https://cdnjs.cloudflare.com/ajax/libs/bulma/0.7.4/css/bulma.css"
FONT_AWESOME = "https://use.fontawesome.com/releases/v5.3.1/js/all.js"
WEB_HTML = """
<html>
    <link rel="stylesheet" href={} />
    <script defer src={}></script>
    <head><title> Interactive Run </title></head>
    <body>
        <div class="columns" style="height: 100%">
            <div class="column is-three-fifths is-offset-one-fifth">
              <section class="hero is-info is-large has-background-light has-text-grey-dark" style="height: 100%">
                <div id="parent" class="hero-body" style="overflow: auto; height: calc(100% - 76px); padding-top: 1em; padding-bottom: 0;">
                    <article class="media">
                      <div class="media-content">
                        <div class="content">
                          <p>
                            <strong>Instructions</strong>
                            <br>
                            Enter a message, and the model will respond interactively.
                          </p>
                        </div>
                      </div>
                    </article>
                </div>
                <div class="hero-foot column is-three-fifths is-offset-one-fifth" style="height: 76px">
                  <form id = "interact">
                      <div class="field is-grouped">
                        <p class="control is-expanded">
                          <input class="input" type="text" id="userIn" placeholder="Type in a message">
                        </p>
                        <p class="control">
                          <button id="respond" type="submit" class="button has-text-white-ter has-background-grey-dark">
                            Submit
                          </button>
                        </p>
                        <p class="control">
                          <button id="restart" type="reset" class="button has-text-white-ter has-background-grey-dark">
                            Restart Conversation
                          </button>
                        </p>
                      </div>
                  </form>
                </div>
              </section>
            </div>
        </div>

        <script>
            function createChatRow(agent, text) {{
                var article = document.createElement("article");
                article.className = "media"

                var figure = document.createElement("figure");
                figure.className = "media-left";

                var span = document.createElement("span");
                span.className = "icon is-large";

                var icon = document.createElement("i");
                icon.className = "fas fas fa-2x" + (agent === "You" ? " fa-user " : agent === "Model" ? " fa-robot" : "");

                var media = document.createElement("div");
                media.className = "media-content";

                var content = document.createElement("div");
                content.className = "content";

                var para = document.createElement("p");
                var paraText = document.createTextNode(text);

                var strong = document.createElement("strong");
                strong.innerHTML = agent;
                var br = document.createElement("br");

                para.appendChild(strong);
                para.appendChild(br);
                para.appendChild(paraText);
                content.appendChild(para);
                media.appendChild(content);

                span.appendChild(icon);
                figure.appendChild(span);

                if (agent !== "Instructions") {{
                    article.appendChild(figure);
                }};

                article.appendChild(media);

                return article;
            }}
            document.getElementById("interact").addEventListener("submit", function(event){{
                event.preventDefault()
                var text = document.getElementById("userIn").value;
                document.getElementById('userIn').value = "";

                fetch('/interact', {{
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    method: 'POST',
                    body: text
                }}).then(response=>response.json()).then(data=>{{
                    var parDiv = document.getElementById("parent");

                    parDiv.append(createChatRow("You", text));

                    // Change info for Model response
                    parDiv.append(createChatRow("Model", data.text));
                    parDiv.scrollTo(0, parDiv.scrollHeight);
                }})
            }});
            document.getElementById("interact").addEventListener("reset", function(event){{
                event.preventDefault()
                var text = document.getElementById("userIn").value;
                document.getElementById('userIn').value = "";

                fetch('/reset', {{
                    headers: {{
                        'Content-Type': 'application/json'
                    }},
                    method: 'POST',
                }}).then(response=>response.json()).then(data=>{{
                    var parDiv = document.getElementById("parent");

                    parDiv.innerHTML = '';
                    parDiv.append(createChatRow("Instructions", "Enter a message, and the model will respond interactively."));
                    parDiv.scrollTo(0, parDiv.scrollHeight);
                }})
            }});
        </script>

    </body>
</html>
"""  # noqa: E501

def setup_interactive(ws):
    SHARED['ws'] = ws


new_message = None
message_available = threading.Event()


class BrowserHandler(BaseHTTPRequestHandler):
    """
    Handle HTTP requests.
    """

    def _interactive_running(self, reply_text):
        data = {}
        data['text'] = reply_text.decode('utf-8')
        if data['text'] == "[DONE]":
            print('[ Closing socket... ]')
            SHARED['ws'].close()
            SHARED['wb'].shutdown()
        json_data = json.dumps(data)
        SHARED['ws'].send(json_data)

    def do_HEAD(self):
        """
        Handle HEAD requests.
        """
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_POST(self):
        """
        Handle POST request, especially replying to a chat message.
        """
        if self.path == '/interact':
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            self._interactive_running(body)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            model_response = {'id': 'Model', 'episode_done': False}
            message_available.wait()
            model_response['text'] = new_message
            message_available.clear()
            json_str = json.dumps(model_response)
            self.wfile.write(bytes(json_str, 'utf-8'))
        elif self.path == '/reset':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(bytes("{}", 'utf-8'))
        else:
            return self._respond({'status': 500})

    def do_GET(self):
        """
        Respond to GET request, especially the initial load.
        """
        paths = {
            '/': {'status': 200},
            '/favicon.ico': {'status': 202},  # Need for chrome
        }
        if self.path in paths:
            self._respond(paths[self.path])
        else:
            self._respond({'status': 500})

    def _handle_http(self, status_code, path, text=None):
        self.send_response(status_code)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        content = WEB_HTML.format(STYLE_SHEET, FONT_AWESOME)
        return bytes(content, 'UTF-8')

    def _respond(self, opts):
        response = self._handle_http(opts['status'], self.path)
        self.wfile.write(response)


def on_message(ws, message):
    """
    Prints the incoming message from the server.

    :param ws: a WebSocketApp
    :param message: json with 'text' field to be printed
    """
    incoming_message = json.loads(message)
    global new_message
    new_message = incoming_message['text']
    message_available.set()


def on_error(ws, error):
    """
    Prints an error, if occurs.

    :param ws: WebSocketApp
    :param error: An error
    """
    print(error)


def on_close(ws):
    """
    Cleanup before closing connection.

    :param ws: WebSocketApp
    """
    # Reset color formatting if necessary
    print("Connection closed")


def _run_browser():
    host = 'localhost'
    serving_port = 8080

    httpd = HTTPServer((host, serving_port), BrowserHandler)

    print('Please connect to the link: http://{}:{}/'.format(host, serving_port))

    SHARED['wb'] = httpd

    httpd.serve_forever()


def on_open(ws):
    """
    Starts a new thread that loops, taking user input and sending it to the websocket.

    :param ws: websocket.WebSocketApp that sends messages to a browser_manager
    """
    threading.Thread(target=_run_browser).start()

if __name__ == "__main__":
    port = 10001
    print("Connecting to port: ", port)
    ws = websocket.WebSocketApp(
        "ws://localhost:{}/websocket".format(port),
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.on_open = on_open
    setup_interactive(ws)
    ws.run_forever()
