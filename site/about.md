---
layout: default
title: About
---
## About {{ site.name }}

<img class="user-avatar" src="{{ site.owner.avatar }}">

I work on distributed-ML systems and interconnect modeling — how collective
communication (`AllReduce`, `AllGather`, …) scales across accelerators and
network fabrics.

This site collects write-ups of experiments. The current one models collective
scaling in [ASTRA-sim](https://github.com/astra-sim/astra-sim) across **torus**
and **switch** topologies on the **analytical** and **ns-3** backends, comparing
**latency-bound** vs **bandwidth-bound** behavior as a function of message size
and node count. Code: [kredd2506/Astro](https://github.com/kredd2506/Astro).

<div class="pagination">
  {% if site.owner.linkedin %}
    <a href="{{ site.owner.linkedin }}" class="social-media-icons"><i class="fa fa-2x fa-linkedin-square" aria-hidden="true"></i></a>
  {% endif %}
  {% if site.owner.email %}
    <a href="mailto:{{ site.owner.email }}" class="social-media-icons"><i class="fa fa-2x fa-envelope-square" aria-hidden="true"></i></a>
  {% endif %}
  {% if site.owner.twitter %}
    <a href="https://twitter.com/{{ site.owner.twitter }}" class="social-media-icons"><i class="fa-brands fa-2x fa-square-x-twitter" aria-hidden="true"></i></a>
  {% endif %}
  {% if site.owner.github %}
    <a href="{{ site.owner.github }}" class="social-media-icons"><i class="fa-brands fa-2x fa-square-github" aria-hidden="true"></i></a>
  {% endif %}
</div>
