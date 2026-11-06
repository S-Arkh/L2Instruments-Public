class StateLabelProbe extends Actor;

var int Counter;

auto state Running
{
Begin:
    if (Counter < 3)
    {
        Counter = Counter + 1;
Again:
        Sleep(0.01);
        Counter = Counter + 1;
        if (Counter < 3)
            goto 'Again';
    }
    else
    {
        Counter = 0;
    }
Done:
    Stop;
}
