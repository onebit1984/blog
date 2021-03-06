---
categories: Computing, Python
date: 2013/02/14 21:42:26
permalink: http://rhodesmill.org/brandon/2013/chunked-wsgi/
title: WSGI and truncated chunked response bodies
---

I may be almost through
with `WSGI <http://www.python.org/dev/peps/pep-3333/>`_.
While it has certainly worked
for a number of my close-to-the-wire HTTP projects over the years,
I seem finally to have reached an edge case where
— as a standard — it cannot guarantee
that I even return a correct response to browsers!

The great triumph of WSGI
is that Python for the Web was suddenly pluggable.
Whether you wrote your application as a raw WSGI callable
or built atop a framework like Django or Pyramid,
you could move from `mod_wsgi <http://code.google.com/p/modwsgi/>`_
running under Apache
to `flup <http://pypi.python.org/pypi/flup/>`_ running behind nginx
to `gunicorn <http://gunicorn.org/>`_ running on Heroku
without batting an eye or rewriting a single line of code.

The great tragedy of WSGI is its complexity.
Despite the fact that there are code examples inlined into its PEP,
it seems that hardly anyone can put together
a fully correct server or piece of middleware.
Writers like Armin Ronacher and Graham Dumpleton
are good sources of complaints on this subject,
as in Graham's recent pair of posts
`WSGI middleware and the hidden write() callable
<http://blog.dscpl.com.au/2012/10/wsgi-middleware-and-hidden-write.html>`_
and `Obligations for calling close() on the iterable returned by a WSGI application
<http://blog.dscpl.com.au/2012/10/obligations-for-calling-close-on.html>`_.
The latter article makes the telling observation that,
“Despite the WSGI specification having been around for so long,
one keeps seeing instances where it is implemented wrongly.”
The problem is that WSGI makes a very awkward gesture toward
asynchronicity — an iterable response body — but lets
the application block while doing all of the rest of its work.
The resulting architecture is still completely unusable
by actual async folks like the Twisted or Tornado teams,
while managing to make life awkward for everybody else.
Add in WSGI's other features,
like an obscure synchronous ``write()`` call
and the ability of the application to call ``start_response()``
several times if it changes its mind,
and correctness starts to become very difficult to achieve.

The great salvation of WSGI
is that hardly anyone actually has to touch it.
Nearly the entire mass
of the world's busy Python web programmers
are protected from the Terrible Secret of WSGI
by working behind some web framework or other.
This lets WSGI's one great benefit shine —
that servers and applications can be plugged into one other
fairly arbitrarily —
without anyone but framework authors
having to wallow in its complexity
and then attend the Web Summit to vent and recuperate.

But, on to my topic for today.

To my great surprise,
it turns out that — for all its complexity —
WSGI manages to be under-specified!
Consider the following application::

    #!python
    def simple_app(environ, start_response):
        headers = [('Content-Type', 'text/plain')]
        start_response('200 OK', headers)

        def content():
            # We start streaming data just fine.
            yield 'The dwarves of yore made mighty spells,'
            yield 'While hammers fell like ringing bells'

            # Then the back-end fails!
            try:
                1/0
            except:
                start_response('500 Error', headers, sys.exc_info())
                return

            # So rest of the response data is not available.
            yield 'In places deep, where dark things sleep,'
            yield 'In hollow halls beneath the fells.'

        return content()

This tiny example manages to exhibit
every essential property of the situation
in which a much larger application has placed me:

* My WSGI application returns a generator,
  instead of waiting until the entire response has been computed
  and returning a list of strings.
  First, this protects my application against situations
  where the entire response body is larger than RAM —
  in which case the approach of queueing strings in a list
  would exhaust memory.
  And second, it lets the web server
  start streaming the response to the client immediately;
  an early version of the design that delayed transmission
  until the whole response body was ready
  often resulted in clients abandoning their connections
  before the first byte of the response body could be sent.

* The application does not know the content-length of the response
  until the final chunk of response body has been generated.

* The response body may be impossible to finish generating,
  but the application will often not learn this
  until it has partially returned the response.
  The back-end service for which it is a mediator
  may return quite a bit of data before going down,
  becoming unresponsive, or returning some kind of error.
  Only at that point does the application learn
  that it cannot, in fact, return a valid response after all.

Many of the resources in play will be cacheable by clients —
some thanks to an ``ETag``
and others thanks to a far-future ``Expires`` header.
This means that returning a truncated response
without any indication of failure
not only ruins the client's current attempt to use the resource,
but might render the client *permanently* unable to proceed
because it might never realize that its cached copy is truncated
and that it needs to re-fetch the resource.

So it is absolutely imperative
that the WSGI server running my application
correctly signal truncated responses to HTTP clients.
There are, to my knowledge, only two ways of doing so.

First, an HTTP server can specify a Content-Length
but then close the socket before sending that much data.
Standards-loving HTTP client libraries
will always recognize failure in this case.
However, one of the limitations that I have already stated
is that I do not know the Content-Length until I have finished
generating and returning the resource, so that is not an option here.

Second, an HTTP server can use chunked encoding
but then close the socket prematurely either
*without* finishing the current chunk,
or by *omitting* the concluding zero-length chunk ``0\r\n\r\n``.
An HTTP client will recognize this as a failure
to receive the entire response.

As you can see in the example app above,
I am doing everything right:

* I am catching the exception instead of letting it propagate
  up into the WSGI server behind me.
  While polite WSGI servers will catch exceptions
  and return 500 status codes to clients,
  there is no guarantee of this,
  and some of them will just let your thread crash
  and leave a dangling open socket behind them!

* I am calling ``start_response()`` with the magic third argument
  that informs the server, on no uncertain terms,
  that I need to terminate the response
  because of an exception.

* The one dicey aspect of this sample application
  is that I am making my second ``start_response()`` call
  from inside of my generator,
  instead of from inside the application function itself.
  This is where we get to the part
  about WSGI not being entirely fully specified:
  it is not entirely clear from the PEP
  whether this is how you terminate a generated response body,
  because the standard does not quite discuss the issue
  of failures that occur after the main callable is complete!

So, that is my situation.

I need to stream large responses without knowing their length
and in circumstances where the client receiving the response
body must always be able to recognize a truncated response
so that they do not run off and try to operate upon
the truncated data.

How do four common WSGI servers stack up
when presented with the sample application above?

* ``wsgiref.simple_server`` — **Complete disaster!**
  When confronted with a generated response body,
  ``wsgiref`` falls back to primitive HTTP/1.0
  that simply appends the response body to the outgoing headers
  and then closes the socket upon completion.
  When confronted with the early termination of my iterator,
  it simply closes the socket early,
  making truncated output indistinguishable from a full response. ::

   HTTP/1.0 200 OK
   Date: Fri, 15 Feb 2013 02:31:32 GMT
   Server: WSGIServer/0.1 Python/2.7.3
   Content-type: text/plain

   The dwarves of yore made mighty spells,
   While hammers fell like ringing bells
   [SOCKET CLOSES]

* ``gevent.pywsgi`` — **Disaster!**
  This popular WSGI server fails in a different way.
  On the one hand,
  it does not create semantic ruin
  by delivering what looks like a valid response:
  it creates a chunked HTTP/1.1 response
  and puts each line of poetry in its own chunk,
  and then never finishes the response —
  after the second line of data, no further data appears.
  So at least clients will not be fooled
  into thinking that the response is complete!
  But it balances this advantage with a downside:
  it actually leaves the socket hanging open indefinitely,
  so after this happens enough times
  your application will run out of file descriptors and crash. ::

   HTTP/1.1 200 OK
   Content-Type: text/plain
   Date: Fri, 15 Feb 2013 02:33:39 GMT
   Transfer-Encoding: chunked

   27
   The dwarves of yore made mighty spells,
   25
   While hammers fell like ringing bells
   [SOCKET STAYS OPEN FOREVER]

* ``gunicorn`` — **Invalid.**
  This is not so bad, though somewhat awkward:
  after sending the first two chunks of an HTTP/1.1 chunked response,
  Gunicorn decides to throw correctness to the wind
  and follow the second chunk with the HTML
  of its standard 500 error message!
  Following an HTTP chunk with anything but a hexadecimal integer
  like ``27\r\n``
  is a violation of the protocol and conforming clients
  will raise an error — but at least there is no chance
  that a client will mistake the response for valid HTTP,
  and the socket does get closed and reclaimed. ::

   HTTP/1.1 200 OK
   Server: gunicorn/0.17.2
   Date: Fri, 15 Feb 2013 02:35:24 GMT
   Connection: close
   Transfer-Encoding: chunked
   Content-type: text/plain

   27
   The dwarves of yore made mighty spells,
   25
   While hammers fell like ringing bells
   HTTP/1.1 500 Internal Server Error
   Connection: close
   Content-Type: text/html
   Content-Length: 134

   <html>
     <head>
       <title>Internal Server Error</title>
     </head>
     <body>
       <h1>Internal Server Error</h1>

     </body>
   </html>
   [SOCKET CLOSES]

* ``cherrypy.wsgiserver`` — well, look at that!
  Robert Brewer will get a beer from me at PyCon this year,
  and CherryPy keeps its reputation as one of the few
  production-ready go-to multi-threaded web servers written in Python.
  (My own reasons for not using it often is because it does not log
  and because I am tired of ``threading`` threads,
  but that is another story.)
  In this case I must admit that it does **everything right:**
  it starts with two HTTP/1.1 chunks and then,
  when my generator fails,
  CherryPy is smart enough to recognize
  that the only correct way to signal failure to the client
  is to *close the socket* without further output. ::

   HTTP/1.1 200 OK
   Content-type: text/plain
   Transfer-Encoding: chunked
   Date: Fri, 15 Feb 2013 02:37:28 GMT
   Server: guinness

   27
   The dwarves of yore made mighty spells,
   25
   While hammers fell like ringing bells
   [SOCKET CLOSES]

I will probably not use CherryPy in this particular application
because, for other reasons, I am building it upon ``gevent``
and have therefore figured out how to work around
the problems with its ``pywsgi`` server
(and will soon be putting those changes together into a pull request).
But it was heartening to see that,
at the very gray edges of the WSGI standard
where HTTP itself needs very careful handling —
since HTTP includes no *explicit* way to say,
“Wait! Never mind! I cannot finish this response after all!” —
that at least one of the WSGI servers on my short-list
manages to put together
the most utterly correct behavior I can think of.

I will let you know which brand of beer Robert chooses.
