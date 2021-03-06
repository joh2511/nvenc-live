#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <iostream>
#include <getopt.h>
#include <vector>

#include "nvenc_config.h"

using namespace std;

/**
 * Process tile bitrates
 * Implementation is sloppy, should be changed to be a file in the future
 */
int* Config::processTileBitrates( const char* tileBitratesStr, int numTiles )
{
	int tbsLen = strlen(tileBitratesStr);
	int* tileBitrates = (int*)malloc(sizeof(int) * numTiles );
	for (int i=0; i<numTiles; i++) {
		// The subtraction converts the '1' or '0' to an int
		tileBitrates[i] = tileBitratesStr[i%tbsLen] - '0';
	}
	this->numTileBitrates = numTiles;
	return tileBitrates;
}

/**
 * Process the command-line arguments to configure the program
 */
void Config::processInput(int argc, char* argv[])
{
    char* bitrateString = 0;

	// Default config options
	this->highBitrate = 1600000;
	this->lowBitrate  =  800000;
	this->numTileCols = 3;
	this->numTileRows = 1;
	this->inputFilename = NULL;
	this->outputFilename = NULL;
	this->width = -1;
	this->height = -1;
	this->fps = -1;
	this->tileBitrates = NULL;
	// Read input
	static struct option long_options[] = {
		{"input", required_argument, 0, 'i'},
		{"output", required_argument, 0, 'o'},
		{"width", required_argument, 0, 'x'},
		{"height", required_argument, 0, 'y'},
		{"fps", required_argument, 0, 'f'},
		{"high-bitrate", required_argument, 0, 'h'},
		{"low-bitrate", required_argument, 0, 'l'},
		{"num-tile-rows", required_argument, 0, 'r'},
		{"num-tile-cols", required_argument, 0, 'c'},
		{"tile-bitrates", required_argument, 0, 't'},
		{0, 0, 0, 0}
	};
	int opt;
	int option_index = 0;
	while ((opt = getopt_long(argc, argv, "i:o:x:y:f:r:c:t:h:l:", long_options, NULL)) != -1) {
		switch (opt) {
			case 'i':
				this->inputFilename = optarg;
				break;
			case 'o':
				this->outputFilename = optarg;
				break;
			case 'x':
				this->width = atoi(optarg);
				break;
			case 'y':
				this->height = atoi(optarg);
				break;
			case 'f':
				this->fps = atof(optarg);
				break;
			case 'h':
				this->highBitrate = atoi(optarg);
				break;
			case 'l':
				this->lowBitrate = atoi(optarg);
				break;
			case 'r':
				this->numTileRows = atoi(optarg);
				break;
			case 'c':
				this->numTileCols = atoi(optarg);
				break;
			case 't':
                bitrateString = strdup( optarg );
				break;
		}
	}
	// Ensure there are no missing parameters
	if (this->inputFilename == NULL ||
		this->outputFilename == NULL ||
		this->width == -1 ||
		this->height == -1 ||
		this->fps == -1 )
    {
		printf("Error: invalid command line parameters. Aborting.\n");
		exit(1);
	}
	int numTiles = this->numTileRows * this->numTileCols;

    if( bitrateString )
    {
	    this->tileBitrates = processTileBitrates( bitrateString, numTiles );
        free( bitrateString );
    }
    else
    {
	    this->tileBitrates = processTileBitrates( "1", numTiles );
    }

	if (this->numTileBitrates != numTiles) {
		printf("Error: incorrect number of tile bitrates specified. Aborting.\n");
		exit(1);
	}
}

int Config::getNumTiles() const
{
    return numTileRows * numTileCols;
}

