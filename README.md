# Reality Bench

A collection of benchmarks of different reality show games. 
With the first implemented benchmark game being "The Traitors".


Implementation Plan

[x] Create a main.py which is the entrpoint to the eval
[x] Implement an enum which has all of the available games for the benchmark (starting with just a single option of 'THE_TRAITORS')
[x] Create a mapping between these enum values and classes for each game.
[x] Define an abstract base class for RealityGame. It should be defined in the following way
    - [x] The constructor should take a unified config which describes the participants of the game. The participants should be a character name and a model which will be backing that specific character
    - [x] Function for starting the game rollout
    - [x] Function for checking the status of the game
    - [x] Function for getting the winner of the game and optionally rank
