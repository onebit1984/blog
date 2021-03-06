---
categories: Python, Computing
date: 2012/03/30 23:34:38
permalink: http://rhodesmill.org/brandon/2012/counting-without-counting/
title: Counting, without counting, in Python
---

It often irks me
that the normal Python pattern for running the body of a loop *n* times
results in the allocation and destruction of *n* integer objects,
even if the body of the loop does not need them.

::

    #!python
    # Creates one million integers

    for i in range(1000000):
        print

    # Creates them one at a time

    for i in xrange(1000000):
        print

Yes, I know, you will rightly complain that I am too easily irked.
The ``range()`` pattern is standard.
The pattern is simple.
The pattern is easy to read.
The implementation is really quite fast
compared to any real work that I might do in the loop.
And, in the bright future when we all use PyPy,
the extra million integer objects will be optimized away anyway.

.. raw:: html

   <!--more-->

But the thought always remained with me that,
whatever the convenience of using a ``range()`` in a ``for`` loop,
it still *meant* something a little heavyhanded:
“create these million integers” for me to loop across.
So while in real life, of course,
I will keep writing my ``for`` loops with ``range()``,
I wondered if there were an alternative with — shall we say —
less *semantic* overhead.

A first alternative, that still creates a list of length *n*
but without creating a million actual objects to loop across,
uses list multiplication to create a million-item list
that is simply a million references to the *same* item
(in this example, the innocuous value ``None``)::

    #!python
    # Creates only the list object

    for i in [None] * 1000000:
        print

Not only does this have the conceptual clarity
of creating only a single extra object for the sake of the iteration,
but some quick experiments with ``timeit``
suggests that this is noticeably faster than using ``range()``
though not quite as fast as using ``xrange()``.
But it still allocates a useless region of memory
whose size must be proportional to the number of iterations we need.

What if we want a solution that is better than O(n)
in the memory it allocates across its lifespan?
Well, had I written this blog post ten years ago,
I could have had a field day building a series
of increasingly complex options
that each used even fewer objects than the last.
One such possibility, just to give you a taste of what might have been,
is to start creating concentric loops::

    #!python
    thousand_things = [None] * 1000
    for i in thousand_things:
        for j in thousand_things:
            print

Here the memory footprint drops to O(√n)
since we have only two lists of a thousand pointers.
Yes, I know, a thousand extra iterator objects will also be created —
one to keep up with each journey across the ``thousand_things`` list
in the inner loop —
but that is still a vast improvement over a million-item list
sitting in memory.

Think of all the fun I would have had
bringing the problem down to O(log n)
by using a list of binary digits
that I decremented using simple list operations.

But it was not to be — because,
when I finally sat down this evening to play,
I discovered within a few minutes that the modern ``itertools`` module
contains a solution that involves not even O(log n)
but actual O(1) memory usage!
Behold, the ``repeat()`` iterator::

    #!python
    # Gives us `None` a million times
    # without creating Python integers!

    from itertools import repeat
    for x in repeat(None, 1000000):
        print

For C Python, this method is the fastest
of the alternatives we have discussed,
as you can quickly verify if you do some ``timeit`` experiments.
For those of you who are new to ``timeit``,
here is a simple command line to get you started::

    #!bash
    $ python -m timeit \
    >  -s 'from itertools import repeat' \
    >  'for x in repeat(None, 1000000): pass'

    100 loops, best of 3: 16.8 msec per loop

So while pursuing an impractical goal,
I did get to learn a useful new ``itertools`` trick
that will probably come in handy someday.
And I can always use ``repeat()`` for iteration, too,
in case I wind up on an embedded device where every byte is precious!
