"""
This file compiles the code in Web Browser Engineering,
up to and including Chapter 10 (Keeping Data Private),
without exercises.
"""

import socket
import ssl
import tkinter
import tkinter.font
import urllib.parse
import dukpy
from lab2 import WIDTH, HEIGHT, HSTEP, VSTEP, SCROLL_STEP
from lab3 import FONTS, get_font
from lab4 import print_tree, HTMLParser
from lab5 import BLOCK_ELEMENTS, DrawRect, DocumentLayout
from lab6 import CSSParser, TagSelector, DescendantSelector
from lab6 import INHERITED_PROPERTIES, style, cascade_priority
from lab6 import DrawText, tree_to_list
from lab7 import DrawLine, DrawOutline, LineLayout, TextLayout, CHROME_PX
from lab8 import URL, Browser, Text, Element
from lab8 import BlockLayout, InputLayout, INPUT_WIDTH_PX
from lab9 import EVENT_DISPATCH_CODE, JSContext, Tab
import wbetools

@wbetools.patch(URL)
class URL:
    def request(self, top_level_url, payload=None):
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        s.connect((self.host, self.port))
    
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
    
        method = "POST" if payload else "GET"
        body = "{} {} HTTP/1.0\r\n".format(method, self.path)
        body += "Host: {}\r\n".format(self.host)
        if self.host in COOKIE_JAR:
            cookie, params = COOKIE_JAR[self.host]
            allow_cookie = True
            if top_level_url and params.get("samesite", "none") == "lax":
                if method != "GET":
                    allow_cookie = self.host == top_level_url.host
            if allow_cookie:
                body += "Cookie: {}\r\n".format(cookie)
        if payload:
            content_length = len(payload.encode("utf8"))
            body += "Content-Length: {}\r\n".format(content_length)
        body += "\r\n" + (payload if payload else "")
        s.send(body.encode("utf8"))
        response = s.makefile("r", encoding="utf8", newline="\r\n")
    
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)
        assert status == "200", "{}: {}".format(status, explanation)
    
        headers = {}
        while True:
            line = response.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            headers[header.lower()] = value.strip()
    
        if "set-cookie" in headers:
            params = {}
            if ";" in headers["set-cookie"]:
                cookie, rest = headers["set-cookie"].split(";", 1)
                for param_pair in rest.split(";"):
                    if '=' in param_pair:
                        name, value = param_pair.strip().split("=", 1)
                        params[name.lower()] = value.lower()
            else:
                cookie = headers["set-cookie"]
            COOKIE_JAR[self.host] = (cookie, params)
    
        assert "transfer-encoding" not in headers
        assert "content-encoding" not in headers
    
        body = response.read()
        s.close()
    
        return headers, body

    def origin(self):
        return self.scheme + "://" + self.host + ":" + str(self.port)
        
COOKIE_JAR = {}

@wbetools.patch(JSContext)
class JSContext:
    def __init__(self, tab):
        self.tab = tab

        self.interp = dukpy.JSInterpreter()
        self.interp.export_function("log", print)
        self.interp.export_function("querySelectorAll",
            self.querySelectorAll)
        self.interp.export_function("getAttribute",
            self.getAttribute)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.export_function("XMLHttpRequest_send",
            self.XMLHttpRequest_send)
        with open("runtime10.js") as f:
            self.interp.evaljs(f.read())

        self.node_to_handle = {}
        self.handle_to_node = {}

    def XMLHttpRequest_send(self, method, url, body):
        full_url = self.tab.url.resolve(url)
        if not self.tab.allowed_request(full_url):
            raise Exception("Cross-origin XHR blocked by CSP")
        headers, out = full_url.request(self.tab.url, body)
        if full_url.origin() != self.tab.url.origin():
            raise Exception("Cross-origin XHR request not allowed")
        return out

@wbetools.patch(Tab)
class Tab:
    def allowed_request(self, url):
        return self.allowed_origins == None or \
            url.origin() in self.allowed_origins

    def load(self, url, body=None):
        headers, body = url.request(self.url, body)
        self.scroll = 0
        self.url = url
        self.history.append(url)

        self.allowed_origins = None
        if "content-security-policy" in headers:
           csp = headers["content-security-policy"].split()
           if len(csp) > 0 and csp[0] == "default-src":
                self.allowed_origins = []
                for origin in csp[1:]:
                    self.allowed_origins.append(URL(origin).origin())

        self.nodes = HTMLParser(body).parse()

        self.js = JSContext(self)
        scripts = [node.attributes["src"] for node
                   in tree_to_list(self.nodes, [])
                   if isinstance(node, Element)
                   and node.tag == "script"
                   and "src" in node.attributes]
        for script in scripts:
            script_url = url.resolve(script)
            if not self.allowed_request(script_url):
                print("Blocked script", script, "due to CSP")
                continue
            header, body = script_url.request(url)
            try:
                self.js.run(body)
            except dukpy.JSRuntimeError as e:
                print("Script", script, "crashed", e)

        self.rules = self.default_style_sheet.copy()
        links = [node.attributes["href"]
                 for node in tree_to_list(self.nodes, [])
                 if isinstance(node, Element)
                 and node.tag == "link"
                 and "href" in node.attributes
                 and node.attributes.get("rel") == "stylesheet"]
        for link in links:
            style_url = url.resolve(link)
            if not self.allowed_request(style_url):
                print("Blocked style", link, "due to CSP")
                continue
            try:
                header, body = style_url.request(url)
            except:
                continue
            self.rules.extend(CSSParser(body).parse())
        self.render()

if __name__ == "__main__":
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()
