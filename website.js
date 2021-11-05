// subscribing to pubNub
const pubnub = new PubNub({
    subscribeKey: 'sub-c-874b9c7a-22a6-11ec-8587-faf056e3304c',
    publishKey: 'pub-c-37ee94e1-4340-4b02-864e-62686f330699' 
});
// Changing the table based on information received
pubnub.subscribe({channels: ['projectGarage']});
pubnub.addListener({
    message: function(m) {
        // console.log(m.message);
        for (let i = 1; i < 5; i++) {
            for (let j = 1; j < 5; j++) {
                // select every table cell from every row
                // console.log('dataRow_' + i + ' td:nth-child(' + j + ')')
                const tableCell = $('#dataRow_' + i + ' td:nth-child(' + j + ')');
                tableCell.text(m.message[i-1][j-1]);
                // colour the row, but keep the original class for eventual later use
                
                if (m.message[i-1][1] == 'yes') {
                    tableCell.addClass('occupiedSpot');
                } else {
                    tableCell.removeClass('occupiedSpot');
                }
            }
        }
    }
})